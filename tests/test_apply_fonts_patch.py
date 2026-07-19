from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "apply_fonts_patch.py"

spec = importlib.util.spec_from_file_location("apply_fonts_patch", SCRIPT)
apply_fonts_patch = importlib.util.module_from_spec(spec)
sys.modules["apply_fonts_patch"] = apply_fonts_patch
assert spec.loader is not None
spec.loader.exec_module(apply_fonts_patch)

FONT_FACE_SET_FIXTURE = '''#include "third_party/blink/renderer/core/css/font_face_set.h"

#include "base/task/single_thread_task_runner.h"
#include "third_party/blink/renderer/bindings/core/v8/script_promise_resolver.h"
#include "third_party/blink/renderer/platform/wtf/text/strcat.h"

namespace blink {

bool FontFaceSet::check(const String& font_string,
                        const String& text,
                        ExceptionState& exception_state) {
  if (!InActiveContext()) {
    return false;
  }

  const Font* font = ResolveFontStyle(font_string);
  if (!font) {
    exception_state.ThrowDOMException(
        DOMExceptionCode::kSyntaxError,
        StrCat({"Could not resolve '", font_string, "' as a font."}));
    return false;
  }

  FontSelector* font_selector = GetFontSelector();
  FontFaceCache* font_face_cache = font_selector->GetFontFaceCache();

  unsigned index = 0;
  while (index < text.length()) {
    UChar32 c = text.CodePointAtOrZero(index);
    index += U16_LENGTH(c);
  }
  return true;
}

}  // namespace blink
'''


class ApplyFontsPatchTests(unittest.TestCase):
    def test_patches_font_face_set_check(self) -> None:
        patched = apply_fonts_patch.patch_font_face_set(FONT_FACE_SET_FIXTURE)

        self.assertIn('#include "base/command_line.h"', patched)
        self.assertIn('BrowseForgeFontFamilyAllowlistDecision', patched)
        self.assertIn('"fingerprint-fonts-list"', patched)
        self.assertIn('switch (BrowseForgeFontFamilyAllowlistDecision(font_string))', patched)
        self.assertIn('if (!BrowseForgeFontListContainsFamily(fonts, family))', patched)
        self.assertIn('const std::unordered_set<std::string>& BrowseForgeFontAllowlistFamilies()', patched)
        self.assertIn('return fonts.find(candidate) != fonts.end();', patched)
        self.assertNotIn('query.find(family)', patched)
        self.assertIn('BrowseForgeFindFontFamilyStart', patched)
        self.assertIn('BrowseForgeIsGenericFontFamily', patched)
        self.assertIn('BrowseForgeSkipOptionalLineHeight', patched)
        self.assertIn('"medium"', patched)
        self.assertIn('"vmin"', patched)
        self.assertIn('case BrowseForgeFontAllowlistDecision::kDenied:', patched)
        self.assertIn('return false;', patched)
        self.assertIn('case BrowseForgeFontAllowlistDecision::kNoAllowlist:', patched)
        self.assertIn('break;', patched)
        self.assertIn('return BrowseForgeFontAllowlistDecision::kDenied;', patched)

    def test_patch_is_idempotent(self) -> None:
        patched_once = apply_fonts_patch.patch_font_face_set(FONT_FACE_SET_FIXTURE)
        patched_twice = apply_fonts_patch.patch_font_face_set(patched_once)

        self.assertEqual(patched_once, patched_twice)

    def test_migrates_prior_allow_return_patch(self) -> None:
        legacy = apply_fonts_patch.patch_font_face_set(FONT_FACE_SET_FIXTURE)
        legacy = legacy.replace(apply_fonts_patch.FONTS_HELPER, apply_fonts_patch.LEGACY_FONTS_HELPER)
        legacy = legacy.replace(apply_fonts_patch.PATCHED_CHECK_PREFIX, apply_fonts_patch.LEGACY_PATCHED_CHECK_PREFIX)

        patched = apply_fonts_patch.patch_font_face_set(legacy)

        self.assertIn('BrowseForgeFontFamilyAllowlistDecision', patched)
        self.assertNotIn('bool BrowseForgeFontFamilyAllowed', patched)
        self.assertNotIn('if (BrowseForgeFontFamilyAllowed(font_string))', patched)
        self.assertIn('case BrowseForgeFontAllowlistDecision::kDenied:', patched)

    def test_migrates_prior_substring_allowlist_patch(self) -> None:
        legacy = apply_fonts_patch.patch_font_face_set(FONT_FACE_SET_FIXTURE)
        legacy = legacy.replace(apply_fonts_patch.FONTS_HELPER, apply_fonts_patch.LEGACY_SUBSTRING_FONTS_HELPER)
        legacy = legacy.replace(apply_fonts_patch.PATCHED_CHECK_PREFIX, apply_fonts_patch.LEGACY_SUBSTRING_PATCHED_CHECK_PREFIX)

        patched = apply_fonts_patch.patch_font_face_set(legacy)

        self.assertIn('BrowseForgeFontFamilyAllowlistDecision(font_string)', patched)
        self.assertIn('const std::unordered_set<std::string>& BrowseForgeFontAllowlistFamilies()', patched)
        self.assertIn('return fonts.find(candidate) != fonts.end();', patched)
        self.assertNotIn('query.find(family)', patched)

    def test_apply_patch_updates_external_checkout_shape(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "src"
            (src / ".git").mkdir(parents=True)
            font_path = src / apply_fonts_patch.FONT_FACE_SET_CC
            font_path.parent.mkdir(parents=True)
            font_path.write_text(FONT_FACE_SET_FIXTURE, encoding="utf-8")

            changed = apply_fonts_patch.apply_patch(src)

            self.assertEqual([apply_fonts_patch.FONT_FACE_SET_CC], changed)
            content = font_path.read_text(encoding="utf-8")
            self.assertIn('fingerprint-fonts-list', content)
            self.assertIn('BrowseForgeFontFamilyAllowlistDecision(font_string)', content)


if __name__ == "__main__":
    unittest.main()
