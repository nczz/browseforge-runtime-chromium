from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "apply_locale_patch.py"

spec = importlib.util.spec_from_file_location("apply_locale_patch", SCRIPT)
apply_locale_patch = importlib.util.module_from_spec(spec)
sys.modules["apply_locale_patch"] = apply_locale_patch
assert spec.loader is not None
spec.loader.exec_module(apply_locale_patch)

NAVIGATOR_LANGUAGE_FIXTURE = '''#include "third_party/blink/renderer/core/frame/navigator_language.h"

#include "base/command_line.h"
#include "services/network/public/cpp/features.h"
#include "third_party/blink/renderer/core/probe/core_probes.h"
#include "third_party/blink/renderer/platform/language.h"

namespace blink {

Vector<String> ParseAndSanitize(const String& accept_languages) {
  Vector<String> languages = accept_languages.SplitSkippingEmpty(',');
  if (languages.empty())
    languages.push_back(DefaultLanguage());
  return languages;
}

bool NavigatorLanguage::IsLanguagesDirty() const {
  // Check if the language has override. If so, consider the language is dirty.
  // This is required, as `IsLanguagesDirty` properly is used to cache
  // v8 value of `languages` in `navigator_language.idl`, while the
  // `languages_dirty_` represents the state of the `languages_`. If `languages`
  // was accessed, the `languages_dirty_` is set to false, but the
  // `navigator_language.idl` still holds the old cached value.
  String accept_languages_override;
  probe::ApplyAcceptLanguageOverride(execution_context_,
                                     &accept_languages_override);

  return languages_dirty_ || !accept_languages_override.IsNull();
}

void NavigatorLanguage::EnsureUpdatedLanguage() {
  String accept_languages_override;
  probe::ApplyAcceptLanguageOverride(execution_context_,
                                     &accept_languages_override);
  if (!accept_languages_override.IsNull()) {
    // If the language has override, force use the override regardless of the
    // `languages_dirty_` state. This is required to allow for workers to
    // respect the override.
    languages_ = ParseAndSanitize(accept_languages_override);
    // Mark the language as dirty, so that if the override is removed, the
    // language will be updated.
    languages_dirty_ = true;
    return;
  }

  if (languages_dirty_) {
    languages_ = ParseAndSanitize(GetAcceptLanguages());
    languages_dirty_ = false;
  }
}

}  // namespace blink
'''


class ApplyLocalePatchTests(unittest.TestCase):
    def test_patches_locale_override(self) -> None:
        patched = apply_locale_patch.patch_locale(NAVIGATOR_LANGUAGE_FIXTURE)

        self.assertIn('BrowseForgeAcceptLanguagesOverride()', patched)
        self.assertIn('"fingerprint-accept-language"', patched)
        self.assertIn('"fingerprint-locale"', patched)
        self.assertIn('languages_ = ParseAndSanitize(browseforge_accept_languages);', patched)
        self.assertIn('return true;', patched)

    def test_patch_is_idempotent(self) -> None:
        patched_once = apply_locale_patch.patch_locale(NAVIGATOR_LANGUAGE_FIXTURE)
        patched_twice = apply_locale_patch.patch_locale(patched_once)

        self.assertEqual(patched_once, patched_twice)
        self.assertEqual(1, patched_once.count("String BrowseForgeAcceptLanguagesOverride()"))

    def test_apply_patch_updates_external_checkout_shape(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "src"
            (src / ".git").mkdir(parents=True)
            language_path = src / apply_locale_patch.NAVIGATOR_LANGUAGE_CC
            language_path.parent.mkdir(parents=True)
            language_path.write_text(NAVIGATOR_LANGUAGE_FIXTURE, encoding="utf-8")

            changed = apply_locale_patch.apply_patch(src)

            self.assertEqual([apply_locale_patch.NAVIGATOR_LANGUAGE_CC], changed)
            self.assertIn("fingerprint-accept-language", language_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
