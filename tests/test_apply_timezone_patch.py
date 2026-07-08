from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "apply_timezone_patch.py"

spec = importlib.util.spec_from_file_location("apply_timezone_patch", SCRIPT)
apply_timezone_patch = importlib.util.module_from_spec(spec)
sys.modules["apply_timezone_patch"] = apply_timezone_patch
assert spec.loader is not None
spec.loader.exec_module(apply_timezone_patch)

TIMEZONE_FIXTURE = '''#include "third_party/blink/renderer/core/timezone/timezone_controller.h"

#include "base/feature_list.h"
#include "third_party/icu/source/i18n/unicode/timezone.h"

namespace blink {

namespace {

BASE_FEATURE(kLazyBlinkTimezoneInit, base::FEATURE_DISABLED_BY_DEFAULT);

String GetCurrentTimezoneId() {
  std::unique_ptr<icu::TimeZone> timezone(icu::TimeZone::createDefault());
  CHECK(timezone);
  return GetTimezoneId(*timezone.get());
}

}  // namespace

TimeZoneController::TimeZoneController() {
  DCHECK(IsMainThread());
  if (!base::FeatureList::IsEnabled(kLazyBlinkTimezoneInit)) {
    host_timezone_id_ = GetCurrentTimezoneId();
  }
}

bool TimeZoneController::SetIcuTimeZoneAndNotifyV8(const String& timezone_id) {
  return !timezone_id.empty();
}

}  // namespace blink
'''


class ApplyTimezonePatchTests(unittest.TestCase):
    def test_patches_timezone_override(self) -> None:
        patched = apply_timezone_patch.patch_timezone(TIMEZONE_FIXTURE)

        self.assertIn('#include "base/command_line.h"', patched)
        self.assertIn('BrowseForgeTimezoneOverride()', patched)
        self.assertIn('"fingerprint-timezone"', patched)
        self.assertIn('SetIcuTimeZoneAndNotifyV8(browseforge_timezone)', patched)
        self.assertIn('host_timezone_id_ = browseforge_timezone;', patched)

    def test_patch_is_idempotent(self) -> None:
        patched_once = apply_timezone_patch.patch_timezone(TIMEZONE_FIXTURE)
        patched_twice = apply_timezone_patch.patch_timezone(patched_once)

        self.assertEqual(patched_once, patched_twice)
        self.assertEqual(1, patched_once.count("String BrowseForgeTimezoneOverride()"))

    def test_apply_patch_updates_external_checkout_shape(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "src"
            (src / ".git").mkdir(parents=True)
            timezone_path = src / apply_timezone_patch.TIMEZONE_CONTROLLER_CC
            timezone_path.parent.mkdir(parents=True)
            timezone_path.write_text(TIMEZONE_FIXTURE, encoding="utf-8")

            changed = apply_timezone_patch.apply_patch(src)

            self.assertEqual([apply_timezone_patch.TIMEZONE_CONTROLLER_CC], changed)
            self.assertIn("fingerprint-timezone", timezone_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
