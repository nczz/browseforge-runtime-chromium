#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_CHROMIUM_SRC = Path("/Users/chun/Projects/browser-source/browseforge-chromium/src")
TIMEZONE_CONTROLLER_CC = Path("third_party/blink/renderer/core/timezone/timezone_controller.cc")

COMMAND_LINE_INCLUDE = '#include "base/command_line.h"\n'
INCLUDE_ANCHOR = '#include "base/feature_list.h"\n'
NAMESPACE_ANCHOR = 'BASE_FEATURE(kLazyBlinkTimezoneInit, base::FEATURE_DISABLED_BY_DEFAULT);\n\n'

TIMEZONE_HELPER = '''String BrowseForgeTimezoneOverride() {\n  const base::CommandLine* command_line =\n      base::CommandLine::ForCurrentProcess();\n  std::string timezone =\n      command_line->GetSwitchValueASCII("fingerprint-timezone");\n  if (timezone.empty() || timezone.size() > 64) {\n    return String();\n  }\n  for (char c : timezone) {\n    const bool valid = (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||\n                       (c >= '0' && c <= '9') || c == '_' || c == '-' ||\n                       c == '+' || c == '/';\n    if (!valid) {\n      return String();\n    }\n  }\n  return String::FromUtf8(timezone);\n}\n\n'''

ORIGINAL_CONSTRUCTOR = '''TimeZoneController::TimeZoneController() {\n  DCHECK(IsMainThread());\n  if (!base::FeatureList::IsEnabled(kLazyBlinkTimezoneInit)) {\n    host_timezone_id_ = GetCurrentTimezoneId();\n  }\n}\n'''
PATCHED_CONSTRUCTOR = '''TimeZoneController::TimeZoneController() {\n  DCHECK(IsMainThread());\n  String browseforge_timezone = BrowseForgeTimezoneOverride();\n  if (!browseforge_timezone.empty() &&\n      SetIcuTimeZoneAndNotifyV8(browseforge_timezone)) {\n    host_timezone_id_ = browseforge_timezone;\n    return;\n  }\n  if (!base::FeatureList::IsEnabled(kLazyBlinkTimezoneInit)) {\n    host_timezone_id_ = GetCurrentTimezoneId();\n  }\n}\n'''


def validate_chromium_src(src: Path) -> None:
    if not (src / ".git").exists():
        raise SystemExit(f"Chromium source checkout is not ready: {src}")
    if not (src / TIMEZONE_CONTROLLER_CC).is_file():
        raise SystemExit(f"Chromium timezone source file is missing: {src / TIMEZONE_CONTROLLER_CC}")


def ensure_include(text: str) -> str:
    if COMMAND_LINE_INCLUDE in text:
        return text
    if INCLUDE_ANCHOR not in text:
        raise SystemExit("timezone_controller.cc include anchor not found")
    return text.replace(INCLUDE_ANCHOR, INCLUDE_ANCHOR + COMMAND_LINE_INCLUDE, 1)


def patch_timezone(text: str) -> str:
    patched = ensure_include(text)
    if "BrowseForgeTimezoneOverride" not in patched:
        if NAMESPACE_ANCHOR not in patched:
            raise SystemExit("timezone_controller.cc helper anchor not found")
        patched = patched.replace(NAMESPACE_ANCHOR, NAMESPACE_ANCHOR + TIMEZONE_HELPER, 1)
    if PATCHED_CONSTRUCTOR in patched:
        return patched
    if ORIGINAL_CONSTRUCTOR not in patched:
        raise SystemExit("TimeZoneController constructor anchor not found")
    return patched.replace(ORIGINAL_CONSTRUCTOR, PATCHED_CONSTRUCTOR, 1)


def write_if_changed(path: Path, content: str) -> bool:
    original = path.read_text(encoding="utf-8")
    if content == original:
        return False
    path.write_text(content, encoding="utf-8")
    return True


def apply_patch(src: Path) -> list[Path]:
    validate_chromium_src(src)
    path = src / TIMEZONE_CONTROLLER_CC
    write_if_changed(path, patch_timezone(path.read_text(encoding="utf-8")))
    return [TIMEZONE_CONTROLLER_CC]


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply BrowseForge timezone source patch")
    parser.add_argument("--chromium-src", type=Path, default=DEFAULT_CHROMIUM_SRC)
    parser.add_argument("--check", action="store_true", help="validate checkout and patch anchors without writing")
    args = parser.parse_args()

    src = args.chromium_src.resolve()
    validate_chromium_src(src)
    if args.check:
        patch_timezone((src / TIMEZONE_CONTROLLER_CC).read_text(encoding="utf-8"))
        print(f"ready: {src / TIMEZONE_CONTROLLER_CC}")
        return
    for path in apply_patch(src):
        print(path.as_posix())


if __name__ == "__main__":
    main()
