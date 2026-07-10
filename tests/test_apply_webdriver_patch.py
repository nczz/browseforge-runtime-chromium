from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "apply_webdriver_patch.py"

spec = importlib.util.spec_from_file_location("apply_webdriver_patch", SCRIPT)
apply_webdriver_patch = importlib.util.module_from_spec(spec)
sys.modules["apply_webdriver_patch"] = apply_webdriver_patch
assert spec.loader is not None
spec.loader.exec_module(apply_webdriver_patch)

NAVIGATOR_FIXTURE = '''#include "third_party/blink/renderer/core/frame/navigator.h"

#include "third_party/blink/renderer/core/probe/core_probes.h"

namespace blink {

bool Navigator::webdriver() const {
  if (RuntimeEnabledFeatures::AutomationControlledEnabled())
    return true;

  bool automation_enabled = false;
  probe::ApplyAutomationOverride(GetExecutionContext(), automation_enabled);
  return automation_enabled;
}

}  // namespace blink
'''


class ApplyWebdriverPatchTests(unittest.TestCase):
    def test_patches_webdriver_behind_browseforge_mode(self) -> None:
        patched = apply_webdriver_patch.patch_navigator(NAVIGATOR_FIXTURE)

        self.assertIn('#include "base/command_line.h"', patched)
        self.assertIn('constexpr char kBrowseForgeStealthModeSwitch[] = "browseforge-stealth-mode";', patched)
        self.assertIn('mode == "enabled"', patched)
        self.assertIn('mode == "strict"', patched)
        self.assertIn('mode == "true"', patched)
        self.assertIn('mode == "1"', patched)
        self.assertNotIn('mode !=', patched)
        self.assertIn("if (BrowseForgeShouldHideWebDriver())\n    return false;", patched)
        self.assertIn("RuntimeEnabledFeatures::AutomationControlledEnabled()", patched)

    def test_patch_is_idempotent(self) -> None:
        patched_once = apply_webdriver_patch.patch_navigator(NAVIGATOR_FIXTURE)
        patched_twice = apply_webdriver_patch.patch_navigator(patched_once)

        self.assertEqual(patched_once, patched_twice)
        self.assertEqual(2, patched_twice.count("BrowseForgeShouldHideWebDriver"))

    def test_apply_patch_updates_external_checkout_shape(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "src"
            (src / ".git").mkdir(parents=True)
            navigator = src / apply_webdriver_patch.NAVIGATOR_CC
            navigator.parent.mkdir(parents=True)
            navigator.write_text(NAVIGATOR_FIXTURE, encoding="utf-8")

            changed = apply_webdriver_patch.apply_patch(src)

            self.assertEqual(apply_webdriver_patch.NAVIGATOR_CC, changed)
            self.assertIn("BrowseForgeShouldHideWebDriver", navigator.read_text(encoding="utf-8"))

    def test_missing_webdriver_anchor_reports_nearest_candidate(self) -> None:
        drifted = NAVIGATOR_FIXTURE.replace(
            "bool Navigator::webdriver() const {",
            "bool Navigator::webdriver(ScriptState*) const {",
        )

        with self.assertRaises(SystemExit) as raised:
            apply_webdriver_patch.patch_navigator(drifted)

        message = str(raised.exception)
        self.assertIn("navigator.webdriver implementation: replacement anchor not found", message)
        self.assertIn("nearest anchor candidate", message)
        self.assertIn("expected-anchor", message)
        self.assertIn("nearest-source", message)


if __name__ == "__main__":
    unittest.main()
