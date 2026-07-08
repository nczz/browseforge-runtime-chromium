from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "apply_screen_patch.py"

spec = importlib.util.spec_from_file_location("apply_screen_patch", SCRIPT)
apply_screen_patch = importlib.util.module_from_spec(spec)
sys.modules["apply_screen_patch"] = apply_screen_patch
assert spec.loader is not None
spec.loader.exec_module(apply_screen_patch)

SCREEN_FIXTURE = '''#include "third_party/blink/renderer/core/frame/screen.h"

#include "base/numerics/safe_conversions.h"
#include "ui/display/screen_info.h"

namespace blink {

Screen::Screen(LocalDOMWindow* window, int64_t display_id)
    : ExecutionContextClient(window), display_id_(display_id) {}

int Screen::height() const {
  if (!DomWindow())
    return 0;
  return GetRect(/*available=*/false).height();
}

int Screen::width() const {
  if (!DomWindow())
    return 0;
  return GetRect(/*available=*/false).width();
}

int Screen::availHeight() const {
  if (!DomWindow())
    return 0;
  return GetRect(/*available=*/true).height();
}

int Screen::availWidth() const {
  if (!DomWindow())
    return 0;
  return GetRect(/*available=*/true).width();
}

}  // namespace blink
'''


class ApplyScreenPatchTests(unittest.TestCase):
    def test_patches_screen_dimensions(self) -> None:
        patched = apply_screen_patch.patch_screen(SCREEN_FIXTURE)

        self.assertIn('#include "base/command_line.h"', patched)
        self.assertIn('#include "base/strings/string_number_conversions.h"', patched)
        self.assertIn('"fingerprint-screen-width"', patched)
        self.assertIn('"fingerprint-screen-height"', patched)
        self.assertIn('"fingerprint-screen-avail-width"', patched)
        self.assertIn('"fingerprint-screen-avail-height"', patched)
        self.assertIn('BrowseForgeScreenSwitchOrDefault(', patched)
        self.assertIn('BrowseForgeScreenAvailSwitchOrDefault(', patched)

    def test_patch_is_idempotent(self) -> None:
        patched_once = apply_screen_patch.patch_screen(SCREEN_FIXTURE)
        patched_twice = apply_screen_patch.patch_screen(patched_once)

        self.assertEqual(patched_once, patched_twice)
        self.assertEqual(1, patched_once.count("bool BrowseForgeReadPositiveIntSwitch"))

    def test_apply_patch_updates_external_checkout_shape(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "src"
            (src / ".git").mkdir(parents=True)
            screen_path = src / apply_screen_patch.SCREEN_CC
            screen_path.parent.mkdir(parents=True)
            screen_path.write_text(SCREEN_FIXTURE, encoding="utf-8")

            changed = apply_screen_patch.apply_patch(src)

            self.assertEqual([apply_screen_patch.SCREEN_CC], changed)
            self.assertIn("fingerprint-screen-width", screen_path.read_text(encoding="utf-8"))
            self.assertIn("fingerprint-screen-avail-height", screen_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
