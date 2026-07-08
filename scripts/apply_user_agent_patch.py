#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_CHROMIUM_SRC = Path("/Users/chun/Projects/browser-source/browseforge-chromium/src")
NAVIGATOR_BASE_CC = Path("third_party/blink/renderer/core/execution_context/navigator_base.cc")
NAVIGATOR_UA_CC = Path("third_party/blink/renderer/core/frame/navigator_ua.cc")

COMMAND_LINE_INCLUDE = '#include "base/command_line.h"\n'
BASE_INCLUDE_ANCHOR = '#include "base/feature_list.h"\n'
UA_INCLUDE_ANCHOR = '#include "base/compiler_specific.h"\n'
BASE_NAMESPACE_ANCHOR = "namespace {\n\n"
UA_NAMESPACE_ANCHOR = "namespace blink {\n\n"

USER_AGENT_HELPER = '''String BrowseForgeNavigatorUserAgentOverride() {
  const base::CommandLine* command_line =
      base::CommandLine::ForCurrentProcess();
  std::string user_agent =
      command_line->GetSwitchValueASCII("fingerprint-user-agent");
  if (user_agent.empty() || user_agent.size() > 512) {
    return String();
  }
  for (unsigned char c : user_agent) {
    if (c < 0x20 || c > 0x7e) {
      return String();
    }
  }
  return String::FromUtf8(user_agent);
}

'''

ORIGINAL_USER_AGENT = '''String NavigatorBase::userAgent() const {
  ExecutionContext* execution_context = GetExecutionContext();
  return execution_context ? execution_context->UserAgent() : String();
}
'''
PATCHED_USER_AGENT = '''String NavigatorBase::userAgent() const {
  String browseforge_user_agent = BrowseForgeNavigatorUserAgentOverride();
  if (!browseforge_user_agent.empty()) {
    return browseforge_user_agent;
  }
  ExecutionContext* execution_context = GetExecutionContext();
  return execution_context ? execution_context->UserAgent() : String();
}
'''

UA_METADATA_HELPER = '''namespace {

bool BrowseForgeIsSafeASCII(const std::string& value, size_t max_size) {
  if (value.empty() || value.size() > max_size) {
    return false;
  }
  for (unsigned char c : value) {
    if (c < 0x20 || c > 0x7e) {
      return false;
    }
  }
  return true;
}

std::string BrowseForgeSwitchString(const char* name, size_t max_size) {
  std::string value =
      base::CommandLine::ForCurrentProcess()->GetSwitchValueASCII(name);
  return BrowseForgeIsSafeASCII(value, max_size) ? value : std::string();
}

std::string BrowseForgeMajorVersion(const std::string& full_version) {
  std::string major = full_version.substr(0, full_version.find('.'));
  if (major.empty() || major.size() > 3) {
    return std::string();
  }
  for (char c : major) {
    if (c < '0' || c > '9') {
      return std::string();
    }
  }
  return major;
}

bool BrowseForgeLooksLikeGreaseBrand(const std::string& brand) {
  return brand.find("Not") != std::string::npos ||
         brand.find(";") != std::string::npos ||
         brand.find(")") != std::string::npos ||
         brand.find("?") != std::string::npos;
}

bool BrowseForgeSwitchBool(const char* name, bool* value) {
  std::string raw =
      base::CommandLine::ForCurrentProcess()->GetSwitchValueASCII(name);
  if (raw == "true" || raw == "1") {
    *value = true;
    return true;
  }
  if (raw == "false" || raw == "0") {
    *value = false;
    return true;
  }
  return false;
}

void BrowseForgeApplyUserAgentMetadataOverrides(UserAgentMetadata& metadata) {
  std::string full_version =
      BrowseForgeSwitchString("fingerprint-ua-full-version", 64);
  if (!full_version.empty()) {
    metadata.full_version = full_version;
    std::string major = BrowseForgeMajorVersion(full_version);
    if (!major.empty()) {
      for (auto& brand_version : metadata.brand_version_list) {
        if (!BrowseForgeLooksLikeGreaseBrand(brand_version.brand)) {
          brand_version.version = major;
        }
      }
      for (auto& brand_version : metadata.brand_full_version_list) {
        if (!BrowseForgeLooksLikeGreaseBrand(brand_version.brand)) {
          brand_version.version = full_version;
        }
      }
    }
  }

  std::string platform = BrowseForgeSwitchString("fingerprint-ua-platform", 64);
  if (!platform.empty()) {
    metadata.platform = platform;
  }
  std::string platform_version =
      BrowseForgeSwitchString("fingerprint-ua-platform-version", 64);
  if (!platform_version.empty()) {
    metadata.platform_version = platform_version;
  }
  std::string architecture =
      BrowseForgeSwitchString("fingerprint-ua-architecture", 32);
  if (!architecture.empty()) {
    metadata.architecture = architecture;
  }
  std::string bitness = BrowseForgeSwitchString("fingerprint-ua-bitness", 16);
  if (!bitness.empty()) {
    metadata.bitness = bitness;
  }
  std::string model = BrowseForgeSwitchString("fingerprint-ua-model", 128);
  if (!model.empty()) {
    metadata.model = model;
  }
  bool bool_value = false;
  if (BrowseForgeSwitchBool("fingerprint-ua-mobile", &bool_value)) {
    metadata.mobile = bool_value;
    metadata.form_factors = {bool_value ? kMobileFormFactor : kDesktopFormFactor};
  }
  if (BrowseForgeSwitchBool("fingerprint-ua-wow64", &bool_value)) {
    metadata.wow64 = bool_value;
  }
}

}  // namespace

'''

ORIGINAL_METADATA = '''  UserAgentMetadata metadata = GetUserAgentMetadata();
  ua_data->SetBrandVersionList(metadata.brand_version_list);
'''
PATCHED_METADATA = '''  UserAgentMetadata metadata = GetUserAgentMetadata();
  BrowseForgeApplyUserAgentMetadataOverrides(metadata);
  ua_data->SetBrandVersionList(metadata.brand_version_list);
'''


def validate_chromium_src(src: Path) -> None:
    if not (src / ".git").exists():
        raise SystemExit(f"Chromium source checkout is not ready: {src}")
    for rel in (NAVIGATOR_BASE_CC, NAVIGATOR_UA_CC):
        if not (src / rel).is_file():
            raise SystemExit(f"Chromium source file is missing: {src / rel}")


def ensure_include(text: str, anchor: str, include: str, label: str) -> str:
    if include in text:
        return text
    if anchor not in text:
        raise SystemExit(f"{label} include anchor not found")
    return text.replace(anchor, anchor + include, 1)


def patch_navigator_base(text: str) -> str:
    patched = ensure_include(text, BASE_INCLUDE_ANCHOR, COMMAND_LINE_INCLUDE, "navigator_base.cc")
    if "BrowseForgeNavigatorUserAgentOverride" not in patched:
        if BASE_NAMESPACE_ANCHOR not in patched:
            raise SystemExit("navigator_base.cc namespace anchor not found")
        patched = patched.replace(BASE_NAMESPACE_ANCHOR, BASE_NAMESPACE_ANCHOR + USER_AGENT_HELPER, 1)
    if PATCHED_USER_AGENT in patched:
        return patched
    if ORIGINAL_USER_AGENT not in patched:
        raise SystemExit("NavigatorBase::userAgent implementation anchor not found")
    return patched.replace(ORIGINAL_USER_AGENT, PATCHED_USER_AGENT, 1)


def patch_navigator_ua(text: str) -> str:
    patched = ensure_include(text, UA_INCLUDE_ANCHOR, COMMAND_LINE_INCLUDE, "navigator_ua.cc")
    if "BrowseForgeApplyUserAgentMetadataOverrides" not in patched:
        if UA_NAMESPACE_ANCHOR not in patched:
            raise SystemExit("navigator_ua.cc namespace anchor not found")
        patched = patched.replace(UA_NAMESPACE_ANCHOR, UA_NAMESPACE_ANCHOR + UA_METADATA_HELPER, 1)
    if PATCHED_METADATA in patched:
        return patched
    if ORIGINAL_METADATA not in patched:
        raise SystemExit("NavigatorUA::userAgentData metadata anchor not found")
    return patched.replace(ORIGINAL_METADATA, PATCHED_METADATA, 1)


def write_if_changed(path: Path, content: str) -> bool:
    original = path.read_text(encoding="utf-8")
    if content == original:
        return False
    path.write_text(content, encoding="utf-8")
    return True


def apply_patch(src: Path) -> list[Path]:
    validate_chromium_src(src)
    changed: list[Path] = []
    base_path = src / NAVIGATOR_BASE_CC
    ua_path = src / NAVIGATOR_UA_CC
    if write_if_changed(base_path, patch_navigator_base(base_path.read_text(encoding="utf-8"))):
        changed.append(NAVIGATOR_BASE_CC)
    if write_if_changed(ua_path, patch_navigator_ua(ua_path.read_text(encoding="utf-8"))):
        changed.append(NAVIGATOR_UA_CC)
    return changed or [NAVIGATOR_BASE_CC, NAVIGATOR_UA_CC]


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply BrowseForge User-Agent and UA-CH source patches")
    parser.add_argument("--chromium-src", type=Path, default=DEFAULT_CHROMIUM_SRC)
    parser.add_argument("--check", action="store_true", help="validate checkout and patch anchors without writing")
    args = parser.parse_args()

    src = args.chromium_src.resolve()
    validate_chromium_src(src)
    if args.check:
        patch_navigator_base((src / NAVIGATOR_BASE_CC).read_text(encoding="utf-8"))
        patch_navigator_ua((src / NAVIGATOR_UA_CC).read_text(encoding="utf-8"))
        print(f"ready: {src / NAVIGATOR_BASE_CC}")
        print(f"ready: {src / NAVIGATOR_UA_CC}")
        return
    for path in apply_patch(src):
        print(path.as_posix())


if __name__ == "__main__":
    main()
