from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "apply_intl_locale_patch.py"

spec = importlib.util.spec_from_file_location("apply_intl_locale_patch", SCRIPT)
apply_intl_locale_patch = importlib.util.module_from_spec(spec)
sys.modules["apply_intl_locale_patch"] = apply_intl_locale_patch
assert spec.loader is not None
spec.loader.exec_module(apply_intl_locale_patch)

ISOLATE_FIXTURE = '''const std::string& Isolate::DefaultLocale() {
  if (default_locale_.empty()) {
    icu::Locale default_locale;
    // Translate ICU's fallback locale to a well-known locale.
    if (strcmp(default_locale.getName(), "en_US_POSIX") == 0 ||
        strcmp(default_locale.getName(), "c") == 0) {
      set_default_locale("en-US");
    } else {
      // Set the locale
      set_default_locale(default_locale.isBogus()
                             ? "und"
                             : Intl::ToLanguageTag(default_locale).FromJust());
    }
    DCHECK(!default_locale_.empty());
  }
  return default_locale_;
}
'''


class ApplyIntlLocalePatchTests(unittest.TestCase):
    def test_patches_v8_default_locale_from_environment(self) -> None:
        patched = apply_intl_locale_patch.patch_isolate(ISOLATE_FIXTURE)

        self.assertIn('getenv("BROWSEFORGE_INTL_LOCALE")', patched)
        self.assertIn('set_default_locale(browseforge_locale);', patched)
        self.assertIn('icu::Locale default_locale;', patched)

    def test_patch_is_idempotent(self) -> None:
        patched_once = apply_intl_locale_patch.patch_isolate(ISOLATE_FIXTURE)
        patched_twice = apply_intl_locale_patch.patch_isolate(patched_once)

        self.assertEqual(patched_once, patched_twice)
        self.assertEqual(1, patched_once.count('BROWSEFORGE_INTL_LOCALE'))

    def test_apply_patch_updates_external_checkout_shape(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "src"
            isolate_path = src / apply_intl_locale_patch.ISOLATE_CC
            isolate_path.parent.mkdir(parents=True)
            isolate_path.write_text(ISOLATE_FIXTURE, encoding="utf-8")

            apply_intl_locale_patch.validate_chromium_src(src)
            patched = apply_intl_locale_patch.patch_isolate(isolate_path.read_text(encoding="utf-8"))
            isolate_path.write_text(patched, encoding="utf-8")

            self.assertIn("BROWSEFORGE_INTL_LOCALE", isolate_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
