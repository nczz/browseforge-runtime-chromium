from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "apply_user_agent_patch.py"

spec = importlib.util.spec_from_file_location("apply_user_agent_patch", SCRIPT)
assert spec and spec.loader
apply_user_agent_patch = importlib.util.module_from_spec(spec)
sys.modules["apply_user_agent_patch"] = apply_user_agent_patch
spec.loader.exec_module(apply_user_agent_patch)

BASE_FIXTURE = '''#include "base/feature_list.h"

namespace blink {

namespace {

String GetReducedNavigatorPlatform() {
  return "Linux x86_64";
}

}  // namespace

String NavigatorBase::userAgent() const {
  ExecutionContext* execution_context = GetExecutionContext();
  return execution_context ? execution_context->UserAgent() : String();
}

String NavigatorBase::platform() const {
  return GetReducedNavigatorPlatform();
}
'''

UA_FIXTURE = '''#include "base/compiler_specific.h"
#include "third_party/blink/public/common/user_agent/user_agent_metadata.h"
#include "third_party/blink/renderer/core/frame/navigator_ua_data.h"
#include "third_party/blink/renderer/platform/wtf/text/wtf_string.h"

namespace blink {

NavigatorUAData* NavigatorUA::userAgentData() {
  NavigatorUAData* ua_data =
      MakeGarbageCollected<NavigatorUAData>(GetUAExecutionContext());

  UserAgentMetadata metadata = GetUserAgentMetadata();
  ua_data->SetBrandVersionList(metadata.brand_version_list);
  ua_data->SetMobile(metadata.mobile);
  ua_data->SetPlatform(String::FromUtf8(metadata.platform),
                       String::FromUtf8(metadata.platform_version));
  ua_data->SetArchitecture(String::FromUtf8(metadata.architecture));
  ua_data->SetModel(String::FromUtf8(metadata.model));
  ua_data->SetUAFullVersion(String::FromUtf8(metadata.full_version));
  ua_data->SetBitness(String::FromUtf8(metadata.bitness));
  ua_data->SetFullVersionList(metadata.brand_full_version_list);
  ua_data->SetWoW64(metadata.wow64);
  Vector<String> form_factors;
  form_factors.reserve(
      base::checked_cast<wtf_size_t>(metadata.form_factors.size()));
  for (auto& ff : metadata.form_factors) {
    form_factors.push_back(String::FromUtf8(ff));
  }
  ua_data->SetFormFactors(std::move(form_factors));

  return ua_data;
}

}  // namespace blink
'''


class ApplyUserAgentPatchTests(unittest.TestCase):
    def test_patches_dom_user_agent_override(self) -> None:
        patched = apply_user_agent_patch.patch_navigator_base(BASE_FIXTURE)
        self.assertIn('GetSwitchValueASCII("fingerprint-user-agent")', patched)
        self.assertIn("BrowseForgeNavigatorUserAgentOverride", patched)
        self.assertIn("if (!browseforge_user_agent.empty())", patched)
        self.assertIn('#include "base/command_line.h"', patched)

    def test_patches_ua_ch_metadata_override(self) -> None:
        patched = apply_user_agent_patch.patch_navigator_ua(UA_FIXTURE)
        self.assertIn("BrowseForgeApplyUserAgentMetadataOverrides(metadata);", patched)
        self.assertIn('BrowseForgeSwitchString("fingerprint-ua-full-version", 64)', patched)
        self.assertIn('BrowseForgeSwitchString("fingerprint-ua-platform", 64)', patched)
        self.assertIn('BrowseForgeSwitchString("fingerprint-ua-architecture", 32)', patched)
        self.assertIn('metadata.form_factors = {bool_value ? kMobileFormFactor : kDesktopFormFactor};', patched)
        self.assertIn("BrowseForgeEnsureFullVersionList(metadata, full_version);", patched)
        self.assertIn("metadata.brand_full_version_list.emplace_back", patched)
        self.assertIn("BrowseForgeFullVersionForBrandVersion", patched)
        self.assertIn('return brand_version.version + ".0.0.0";', patched)
        self.assertIn("ua_data->SetFullVersionList(metadata.brand_full_version_list);", patched)

    def test_patch_is_idempotent(self) -> None:
        patched_base_once = apply_user_agent_patch.patch_navigator_base(BASE_FIXTURE)
        patched_base_twice = apply_user_agent_patch.patch_navigator_base(patched_base_once)
        self.assertEqual(patched_base_once, patched_base_twice)
        patched_ua_once = apply_user_agent_patch.patch_navigator_ua(UA_FIXTURE)
        patched_ua_twice = apply_user_agent_patch.patch_navigator_ua(patched_ua_once)
        self.assertEqual(patched_ua_once, patched_ua_twice)

    def test_upgrades_existing_ua_ch_patch_with_full_version_list_seed(self) -> None:
        patched_once = apply_user_agent_patch.patch_navigator_ua(UA_FIXTURE)
        old_patch = patched_once.replace(
            "      BrowseForgeEnsureFullVersionList(metadata, full_version);\n",
            "",
        )
        helper_start = old_patch.index("void BrowseForgeEnsureFullVersionList")
        helper_end = old_patch.index("bool BrowseForgeSwitchBool", helper_start)
        old_patch = old_patch[:helper_start] + old_patch[helper_end:]
        upgraded = apply_user_agent_patch.patch_navigator_ua(old_patch)
        self.assertIn("BrowseForgeEnsureFullVersionList(metadata, full_version);", upgraded)
        self.assertIn("void BrowseForgeEnsureFullVersionList", upgraded)
        self.assertIn("metadata.brand_full_version_list.emplace_back", upgraded)
        self.assertIn("BrowseForgeFullVersionForBrandVersion", upgraded)
        self.assertIn('return brand_version.version + ".0.0.0";', upgraded)

    def test_apply_patch_updates_external_checkout_shape(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "src"
            base_path = src / apply_user_agent_patch.NAVIGATOR_BASE_CC
            ua_path = src / apply_user_agent_patch.NAVIGATOR_UA_CC
            base_path.parent.mkdir(parents=True)
            ua_path.parent.mkdir(parents=True)
            (src / ".git").mkdir()
            base_path.write_text(BASE_FIXTURE, encoding="utf-8")
            ua_path.write_text(UA_FIXTURE, encoding="utf-8")
            changed = apply_user_agent_patch.apply_patch(src)
            self.assertEqual(
                [
                    apply_user_agent_patch.NAVIGATOR_BASE_CC,
                    apply_user_agent_patch.NAVIGATOR_UA_CC,
                ],
                changed,
            )
            self.assertIn("fingerprint-user-agent", base_path.read_text(encoding="utf-8"))
            self.assertIn("fingerprint-ua-full-version", ua_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
