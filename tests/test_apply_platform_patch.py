from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "apply_platform_patch.py"

spec = importlib.util.spec_from_file_location("apply_platform_patch", SCRIPT)
apply_platform_patch = importlib.util.module_from_spec(spec)
sys.modules["apply_platform_patch"] = apply_platform_patch
assert spec.loader is not None
spec.loader.exec_module(apply_platform_patch)

NAVIGATOR_BASE_FIXTURE = '''#include "third_party/blink/renderer/core/execution_context/navigator_base.h"

#include "base/feature_list.h"
#include "build/build_config.h"
#include "third_party/blink/renderer/platform/runtime_enabled_features.h"

namespace blink {

namespace {

String GetReducedNavigatorPlatform() {
  return "Linux x86_64";
}

}  // namespace

String NavigatorBase::platform() const {
#if BUILDFLAG(IS_ANDROID)
  // We need to check the ReduceUserAgentMinorVersion feature flag for
  // Android WebView, which does not currently ship a reduced User-Agent.
  if (!RuntimeEnabledFeatures::ReduceUserAgentMinorVersionEnabled()) {
    return NavigatorID::platform();
  }
#endif
  return GetReducedNavigatorPlatform();
}

}  // namespace blink
'''


class ApplyPlatformPatchTests(unittest.TestCase):
    def test_patches_platform_override(self) -> None:
        patched = apply_platform_patch.patch_platform(NAVIGATOR_BASE_FIXTURE)

        self.assertIn('#include "base/command_line.h"', patched)
        self.assertIn('BrowseForgeNavigatorPlatformOverride()', patched)
        self.assertIn('"fingerprint-platform"', patched)
        self.assertIn('String browseforge_platform = BrowseForgeNavigatorPlatformOverride();', patched)
        self.assertIn('return browseforge_platform;', patched)

    def test_patch_is_idempotent(self) -> None:
        patched_once = apply_platform_patch.patch_platform(NAVIGATOR_BASE_FIXTURE)
        patched_twice = apply_platform_patch.patch_platform(patched_once)

        self.assertEqual(patched_once, patched_twice)
        self.assertEqual(1, patched_once.count("String BrowseForgeNavigatorPlatformOverride()"))

    def test_apply_patch_updates_external_checkout_shape(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "src"
            (src / ".git").mkdir(parents=True)
            navigator_path = src / apply_platform_patch.NAVIGATOR_BASE_CC
            navigator_path.parent.mkdir(parents=True)
            navigator_path.write_text(NAVIGATOR_BASE_FIXTURE, encoding="utf-8")

            changed = apply_platform_patch.apply_patch(src)

            self.assertEqual([apply_platform_patch.NAVIGATOR_BASE_CC], changed)
            self.assertIn("fingerprint-platform", navigator_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
