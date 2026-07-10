from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "apply_feature_parity_patch.py"

spec = importlib.util.spec_from_file_location("apply_feature_parity_patch", SCRIPT)
apply_feature_parity_patch = importlib.util.module_from_spec(spec)
sys.modules["apply_feature_parity_patch"] = apply_feature_parity_patch
assert spec.loader is not None
spec.loader.exec_module(apply_feature_parity_patch)

FEATURES_FIXTURE = '''features: [
    {
      name: "ContactsManager",
      status:  {"Android": "stable", "default": "test"},
    },
    {
      name: "ContactsManagerExtraProperties",
      status:  {"Android": "stable", "default": "test"},
    },
    {
      name: "ContentIndex",
      status:  {"Android": "stable", "default": "experimental"},
    },
    {
      name: "NetInfoDownlinkMax",
      public: true,
      // Only Android, ChromeOS support NetInfo downlinkMax, type and ontypechange now
      status: {
        "Android": "stable",
        "ChromeOS": "stable",
        "default": "experimental",
      },
      base_feature: "none",
    },
    {
      name: "SerialPortConnected",
      status: {"Android": "", "default": "experimental"},
      base_feature: "none",
    },
]
'''


class ApplyFeatureParityPatchTests(unittest.TestCase):
    def test_patches_desktop_feature_defaults(self) -> None:
        patched = apply_feature_parity_patch.patch_runtime_features(FEATURES_FIXTURE)

        self.assertIn('name: "ContactsManager"', patched)
        self.assertIn('name: "ContactsManagerExtraProperties"', patched)
        self.assertIn('name: "ContentIndex"', patched)
        self.assertIn('name: "NetInfoDownlinkMax"', patched)
        self.assertNotIn('"default": "test"', patched)
        self.assertNotIn('"default": "experimental"', patched)
        self.assertEqual(patched.count('status: "stable"'), 5)

    def test_patch_is_idempotent(self) -> None:
        patched_once = apply_feature_parity_patch.patch_runtime_features(FEATURES_FIXTURE)
        patched_twice = apply_feature_parity_patch.patch_runtime_features(patched_once)

        self.assertEqual(patched_once, patched_twice)

    def test_apply_patch_updates_external_checkout_shape(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "src"
            (src / ".git").mkdir(parents=True)
            features_path = src / apply_feature_parity_patch.RUNTIME_FEATURES_JSON5
            features_path.parent.mkdir(parents=True)
            features_path.write_text(FEATURES_FIXTURE, encoding="utf-8")

            changed = apply_feature_parity_patch.apply_patch(src)

            self.assertEqual([apply_feature_parity_patch.RUNTIME_FEATURES_JSON5], changed)
            content = features_path.read_text(encoding="utf-8")
            self.assertIn('name: "ContentIndex"', content)
            self.assertIn('BrowseForge enables this desktop parity surface', content)
            self.assertIn('name: "SerialPortConnected"', content)
            self.assertIn("desktop serial feature inventory coherent", content)
            self.assertNotIn('"default": "experimental"', content)


if __name__ == "__main__":
    unittest.main()
