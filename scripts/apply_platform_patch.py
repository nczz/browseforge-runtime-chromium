#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_CHROMIUM_SRC = Path("/Users/chun/Projects/browser-source/browseforge-chromium/src")
NAVIGATOR_BASE_CC = Path("third_party/blink/renderer/core/execution_context/navigator_base.cc")

COMMAND_LINE_INCLUDE = '#include "base/command_line.h"\n'
INCLUDE_ANCHOR = '#include "base/feature_list.h"\n'
NAMESPACE_ANCHOR = 'namespace {\n\n'

PLATFORM_HELPER = '''String BrowseForgeNavigatorPlatformOverride() {\n  const base::CommandLine* command_line =\n      base::CommandLine::ForCurrentProcess();\n  std::string platform =\n      command_line->GetSwitchValueASCII("fingerprint-platform");\n  if (platform.empty() || platform.size() > 64) {\n    return String();\n  }\n  for (char c : platform) {\n    const bool valid = (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||\n                       (c >= '0' && c <= '9') || c == '_' || c == '-' ||\n                       c == ' ' || c == '.';\n    if (!valid) {\n      return String();\n    }\n  }\n  return String::FromUtf8(platform);\n}\n\n'''

ORIGINAL_PLATFORM = '''String NavigatorBase::platform() const {\n#if BUILDFLAG(IS_ANDROID)\n  // We need to check the ReduceUserAgentMinorVersion feature flag for\n  // Android WebView, which does not currently ship a reduced User-Agent.\n  if (!RuntimeEnabledFeatures::ReduceUserAgentMinorVersionEnabled()) {\n    return NavigatorID::platform();\n  }\n#endif\n  return GetReducedNavigatorPlatform();\n}\n'''
PATCHED_PLATFORM = '''String NavigatorBase::platform() const {\n  String browseforge_platform = BrowseForgeNavigatorPlatformOverride();\n  if (!browseforge_platform.empty()) {\n    return browseforge_platform;\n  }\n#if BUILDFLAG(IS_ANDROID)\n  // We need to check the ReduceUserAgentMinorVersion feature flag for\n  // Android WebView, which does not currently ship a reduced User-Agent.\n  if (!RuntimeEnabledFeatures::ReduceUserAgentMinorVersionEnabled()) {\n    return NavigatorID::platform();\n  }\n#endif\n  return GetReducedNavigatorPlatform();\n}\n'''


def validate_chromium_src(src: Path) -> None:
    if not (src / ".git").exists():
        raise SystemExit(f"Chromium source checkout is not ready: {src}")
    if not (src / NAVIGATOR_BASE_CC).is_file():
        raise SystemExit(f"Chromium navigator base source file is missing: {src / NAVIGATOR_BASE_CC}")


def ensure_include(text: str) -> str:
    if COMMAND_LINE_INCLUDE in text:
        return text
    if INCLUDE_ANCHOR not in text:
        raise SystemExit("navigator_base.cc include anchor not found")
    return text.replace(INCLUDE_ANCHOR, INCLUDE_ANCHOR + COMMAND_LINE_INCLUDE, 1)


def patch_platform(text: str) -> str:
    patched = ensure_include(text)
    if "BrowseForgeNavigatorPlatformOverride" not in patched:
        if NAMESPACE_ANCHOR not in patched:
            raise SystemExit("navigator_base.cc namespace anchor not found")
        patched = patched.replace(NAMESPACE_ANCHOR, NAMESPACE_ANCHOR + PLATFORM_HELPER, 1)
    if PATCHED_PLATFORM in patched:
        return patched
    if ORIGINAL_PLATFORM not in patched:
        raise SystemExit("NavigatorBase::platform implementation anchor not found")
    return patched.replace(ORIGINAL_PLATFORM, PATCHED_PLATFORM, 1)


def write_if_changed(path: Path, content: str) -> bool:
    original = path.read_text(encoding="utf-8")
    if content == original:
        return False
    path.write_text(content, encoding="utf-8")
    return True


def apply_patch(src: Path) -> list[Path]:
    validate_chromium_src(src)
    path = src / NAVIGATOR_BASE_CC
    write_if_changed(path, patch_platform(path.read_text(encoding="utf-8")))
    return [NAVIGATOR_BASE_CC]


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply BrowseForge navigator.platform source patch")
    parser.add_argument("--chromium-src", type=Path, default=DEFAULT_CHROMIUM_SRC)
    parser.add_argument("--check", action="store_true", help="validate checkout and patch anchors without writing")
    args = parser.parse_args()

    src = args.chromium_src.resolve()
    validate_chromium_src(src)
    if args.check:
        patch_platform((src / NAVIGATOR_BASE_CC).read_text(encoding="utf-8"))
        print(f"ready: {src / NAVIGATOR_BASE_CC}")
        return
    for path in apply_patch(src):
        print(path.as_posix())


if __name__ == "__main__":
    main()
