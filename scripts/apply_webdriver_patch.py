#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_CHROMIUM_SRC = Path("/Users/chun/Projects/browser-source/browseforge-chromium/src")
NAVIGATOR_CC = Path("third_party/blink/renderer/core/frame/navigator.cc")

COMMAND_LINE_INCLUDE = '#include "base/command_line.h"\n'
INCLUDE_ANCHOR = '#include "third_party/blink/renderer/core/frame/navigator.h"\n'

HELPER = '''\nnamespace {\n\nconstexpr char kBrowseForgeStealthModeSwitch[] = "browseforge-stealth-mode";\nconstexpr char kBrowseForgeStealthModeOff[] = "off";\n\nbool BrowseForgeShouldHideWebDriver() {\n  const base::CommandLine* command_line =\n      base::CommandLine::ForCurrentProcess();\n  if (!command_line->HasSwitch(kBrowseForgeStealthModeSwitch))\n    return false;\n  return command_line->GetSwitchValueASCII(kBrowseForgeStealthModeSwitch) !=\n         kBrowseForgeStealthModeOff;\n}\n\n}  // namespace\n'''
NAMESPACE_ANCHOR = "namespace blink {\n"

ORIGINAL_WEBDRIVER = '''bool Navigator::webdriver() const {\n  if (RuntimeEnabledFeatures::AutomationControlledEnabled())\n    return true;\n\n  bool automation_enabled = false;\n  probe::ApplyAutomationOverride(GetExecutionContext(), automation_enabled);\n  return automation_enabled;\n}\n'''
PATCHED_WEBDRIVER = '''bool Navigator::webdriver() const {\n  if (BrowseForgeShouldHideWebDriver())\n    return false;\n\n  if (RuntimeEnabledFeatures::AutomationControlledEnabled())\n    return true;\n\n  bool automation_enabled = false;\n  probe::ApplyAutomationOverride(GetExecutionContext(), automation_enabled);\n  return automation_enabled;\n}\n'''


def validate_chromium_src(src: Path) -> None:
    if not (src / ".git").exists():
        raise SystemExit(f"Chromium source checkout is not ready: {src}")
    if not (src / NAVIGATOR_CC).is_file():
        raise SystemExit(f"navigator.cc is missing: {src / NAVIGATOR_CC}")


def patch_navigator(text: str) -> str:
    patched = text
    if COMMAND_LINE_INCLUDE not in patched:
        if INCLUDE_ANCHOR not in patched:
            raise SystemExit("navigator.cc include anchor not found")
        patched = patched.replace(INCLUDE_ANCHOR, INCLUDE_ANCHOR + "\n" + COMMAND_LINE_INCLUDE, 1)

    if "BrowseForgeShouldHideWebDriver" not in patched:
        if NAMESPACE_ANCHOR not in patched:
            raise SystemExit("navigator.cc namespace anchor not found")
        patched = patched.replace(NAMESPACE_ANCHOR, HELPER + "\n" + NAMESPACE_ANCHOR, 1)

    if PATCHED_WEBDRIVER in patched:
        return patched
    if ORIGINAL_WEBDRIVER not in patched:
        raise SystemExit("navigator.webdriver implementation anchor not found")
    return patched.replace(ORIGINAL_WEBDRIVER, PATCHED_WEBDRIVER, 1)


def apply_patch(src: Path) -> Path:
    validate_chromium_src(src)
    navigator = src / NAVIGATOR_CC
    original = navigator.read_text(encoding="utf-8")
    patched = patch_navigator(original)
    if patched != original:
        navigator.write_text(patched, encoding="utf-8")
    return NAVIGATOR_CC


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply BrowseForge navigator.webdriver source patch")
    parser.add_argument("--chromium-src", type=Path, default=DEFAULT_CHROMIUM_SRC)
    parser.add_argument("--check", action="store_true", help="validate checkout and patch anchors without writing")
    args = parser.parse_args()

    src = args.chromium_src.resolve()
    validate_chromium_src(src)
    if args.check:
        patch_navigator((src / NAVIGATOR_CC).read_text(encoding="utf-8"))
        print(f"ready: {src / NAVIGATOR_CC}")
        return
    print(apply_patch(src).as_posix())


if __name__ == "__main__":
    main()
