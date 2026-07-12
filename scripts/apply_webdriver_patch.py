#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from patch_ops import ensure_text_after, ensure_text_before, replace_once, write_if_changed

DEFAULT_CHROMIUM_SRC = Path("/Users/chun/Projects/browser-source/browseforge-chromium/src")
NAVIGATOR_CC = Path("third_party/blink/renderer/core/frame/navigator.cc")

COMMAND_LINE_INCLUDE = '#include "base/command_line.h"\n'
INCLUDE_ANCHOR = '#include "third_party/blink/renderer/core/frame/navigator.h"\n'

HELPER = '''
namespace {

constexpr char kBrowseForgeStealthModeSwitch[] = "browseforge-stealth-mode";

bool BrowseForgeShouldHideWebDriver() {
  const base::CommandLine* command_line =
      base::CommandLine::ForCurrentProcess();
  if (!command_line->HasSwitch(kBrowseForgeStealthModeSwitch))
    return false;
  const std::string mode =
      command_line->GetSwitchValueASCII(kBrowseForgeStealthModeSwitch);
  return mode == "enabled" || mode == "strict" || mode == "true" ||
         mode == "1";
}

}  // namespace
'''
NAMESPACE_ANCHOR = "namespace blink {\n"

ORIGINAL_WEBDRIVER = '''bool Navigator::webdriver() const {\n  if (RuntimeEnabledFeatures::AutomationControlledEnabled())\n    return true;\n\n  bool automation_enabled = false;\n  probe::ApplyAutomationOverride(GetExecutionContext(), automation_enabled);\n  return automation_enabled;\n}\n'''
PATCHED_WEBDRIVER = '''bool Navigator::webdriver() const {\n  if (BrowseForgeShouldHideWebDriver())\n    return false;\n\n  if (RuntimeEnabledFeatures::AutomationControlledEnabled())\n    return true;\n\n  bool automation_enabled = false;\n  probe::ApplyAutomationOverride(GetExecutionContext(), automation_enabled);\n  return automation_enabled;\n}\n'''


def validate_chromium_src(src: Path) -> None:
    if not (src / ".git").exists():
        raise SystemExit(f"Chromium source checkout is not ready: {src}")
    if not (src / NAVIGATOR_CC).is_file():
        raise SystemExit(f"navigator.cc is missing: {src / NAVIGATOR_CC}")


def normalize_webdriver_helper(text: str) -> str:
    helper_name = "BrowseForgeShouldHideWebDriver"
    helper_index = text.find(helper_name)
    if helper_index == -1:
        return text
    start = text.rfind("namespace {", 0, helper_index)
    end_marker = "}  // namespace"
    end = text.find(end_marker, helper_index)
    if start == -1 or end == -1:
        raise SystemExit("navigator.cc existing BrowseForge webdriver helper block not found")
    end += len(end_marker)
    return text[:start] + HELPER.strip("\n") + text[end:]


def patch_navigator(text: str) -> str:
    patched = ensure_text_after(
        text,
        INCLUDE_ANCHOR,
        "\n" + COMMAND_LINE_INCLUDE,
        "navigator.cc include",
    )
    patched = normalize_webdriver_helper(patched)
    if "BrowseForgeShouldHideWebDriver" not in patched:
        patched = ensure_text_before(
            patched,
            NAMESPACE_ANCHOR,
            HELPER + "\n",
            "navigator.cc namespace",
        )
    return replace_once(
        patched,
        ORIGINAL_WEBDRIVER,
        PATCHED_WEBDRIVER,
        "navigator.webdriver implementation",
    )


def apply_patch(src: Path) -> Path:
    validate_chromium_src(src)
    navigator = src / NAVIGATOR_CC
    patched = patch_navigator(navigator.read_text(encoding="utf-8"))
    write_if_changed(navigator, patched)
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
