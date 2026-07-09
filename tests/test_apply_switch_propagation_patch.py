from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "apply_switch_propagation_patch.py"

spec = importlib.util.spec_from_file_location("apply_switch_propagation_patch", SCRIPT)
assert spec and spec.loader
apply_switch_propagation_patch = importlib.util.module_from_spec(spec)
sys.modules["apply_switch_propagation_patch"] = apply_switch_propagation_patch
spec.loader.exec_module(apply_switch_propagation_patch)

RENDER_HOST_FIXTURE = '''void RenderProcessHostImpl::PropagateBrowserCommandLineToRenderer(
    const base::CommandLine& browser_cmd,
    base::CommandLine* renderer_cmd) {
  static const char* const kSwitchNames[] = {
      switches::kDisableInProcessStackTraces,
  };
  renderer_cmd->CopySwitchesFrom(browser_cmd, kSwitchNames);
}
'''


class ApplySwitchPropagationPatchTests(unittest.TestCase):
    def test_adds_browseforge_switches_to_renderer_allowlist(self) -> None:
        patched = apply_switch_propagation_patch.patch_switch_propagation(RENDER_HOST_FIXTURE)
        self.assertIn('"fingerprint-timezone"', patched)
        self.assertIn('"fingerprint-hardware-concurrency"', patched)
        self.assertIn('"fingerprint-device-memory"', patched)
        self.assertIn('"fingerprint-webgl-renderer"', patched)
        self.assertIn('"browseforge-stealth-mode"', patched)
        self.assertLess(patched.index('"fingerprint"'), patched.index("switches::kDisableInProcessStackTraces"))

    def test_patch_is_idempotent(self) -> None:
        patched_once = apply_switch_propagation_patch.patch_switch_propagation(RENDER_HOST_FIXTURE)
        patched_twice = apply_switch_propagation_patch.patch_switch_propagation(patched_once)
        self.assertEqual(patched_once, patched_twice)

    def test_apply_patch_updates_external_checkout_shape(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "src"
            path = src / apply_switch_propagation_patch.RENDER_PROCESS_HOST_IMPL_CC
            path.parent.mkdir(parents=True)
            (src / ".git").mkdir()
            path.write_text(RENDER_HOST_FIXTURE, encoding="utf-8")
            changed = apply_switch_propagation_patch.apply_patch(src)
            self.assertEqual([apply_switch_propagation_patch.RENDER_PROCESS_HOST_IMPL_CC], changed)
            text = path.read_text(encoding="utf-8")
            self.assertIn('"fingerprint-timezone"', text)


if __name__ == "__main__":
    unittest.main()
