from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "apply_hardware_patch.py"

spec = importlib.util.spec_from_file_location("apply_hardware_patch", SCRIPT)
apply_hardware_patch = importlib.util.module_from_spec(spec)
sys.modules["apply_hardware_patch"] = apply_hardware_patch
assert spec.loader is not None
spec.loader.exec_module(apply_hardware_patch)

BASE_FIXTURE = '''#include "third_party/blink/renderer/core/execution_context/navigator_base.h"

#include "base/feature_list.h"
#include "third_party/blink/renderer/core/frame/navigator_concurrent_hardware.h"
#include "third_party/blink/renderer/core/probe/core_probes.h"

namespace blink {

namespace {

String GetReducedNavigatorPlatform() {
  return "Linux x86_64";
}

}  // namespace

unsigned int NavigatorBase::hardwareConcurrency() const {
  unsigned int hardware_concurrency =
      NavigatorConcurrentHardware::hardwareConcurrency();

  probe::ApplyHardwareConcurrencyOverride(
      probe::ToCoreProbeSink(GetExecutionContext()), hardware_concurrency);
  return hardware_concurrency;
}

}  // namespace blink
'''

DEVICE_FIXTURE = '''#include "third_party/blink/renderer/core/frame/navigator_device_memory.h"

#include "third_party/blink/public/common/device_memory/approximated_device_memory.h"

namespace blink {

float NavigatorDeviceMemory::deviceMemory() const {
  return ApproximatedDeviceMemory::GetApproximatedDeviceMemory();
}

}  // namespace blink
'''


class ApplyHardwarePatchTests(unittest.TestCase):
    def test_patches_hardware_concurrency(self) -> None:
        patched = apply_hardware_patch.patch_hardware_concurrency(BASE_FIXTURE)

        self.assertIn('#include "base/command_line.h"', patched)
        self.assertIn('#include "base/strings/string_number_conversions.h"', patched)
        self.assertIn('"fingerprint-hardware-concurrency"', patched)
        self.assertIn('BrowseForgeHardwareConcurrencyOverrideOrDefault(', patched)
        self.assertIn('NavigatorConcurrentHardware::hardwareConcurrency())', patched)

    def test_patches_device_memory(self) -> None:
        patched = apply_hardware_patch.patch_device_memory(DEVICE_FIXTURE)

        self.assertIn('"fingerprint-device-memory"', patched)
        self.assertIn('BrowseForgeDeviceMemoryOverrideOrDefault(', patched)
        self.assertIn('ApproximatedDeviceMemory::GetApproximatedDeviceMemory())', patched)

    def test_patches_are_idempotent(self) -> None:
        base_once = apply_hardware_patch.patch_hardware_concurrency(BASE_FIXTURE)
        base_twice = apply_hardware_patch.patch_hardware_concurrency(base_once)
        device_once = apply_hardware_patch.patch_device_memory(DEVICE_FIXTURE)
        device_twice = apply_hardware_patch.patch_device_memory(device_once)

        self.assertEqual(base_once, base_twice)
        self.assertEqual(device_once, device_twice)

    def test_apply_patch_updates_external_checkout_shape(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "src"
            (src / ".git").mkdir(parents=True)
            base_path = src / apply_hardware_patch.NAVIGATOR_BASE_CC
            device_path = src / apply_hardware_patch.NAVIGATOR_DEVICE_MEMORY_CC
            base_path.parent.mkdir(parents=True)
            device_path.parent.mkdir(parents=True)
            base_path.write_text(BASE_FIXTURE, encoding="utf-8")
            device_path.write_text(DEVICE_FIXTURE, encoding="utf-8")

            changed = apply_hardware_patch.apply_patch(src)

            self.assertIn(apply_hardware_patch.NAVIGATOR_BASE_CC, changed)
            self.assertIn(apply_hardware_patch.NAVIGATOR_DEVICE_MEMORY_CC, changed)
            self.assertIn("fingerprint-hardware-concurrency", base_path.read_text(encoding="utf-8"))
            self.assertIn("fingerprint-device-memory", device_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
