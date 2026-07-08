#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_CHROMIUM_SRC = Path("/Users/chun/Projects/browser-source/browseforge-chromium/src")
SCREEN_CC = Path("third_party/blink/renderer/core/frame/screen.cc")

COMMAND_LINE_INCLUDE = '#include "base/command_line.h"\n'
STRING_CONVERSIONS_INCLUDE = '#include "base/strings/string_number_conversions.h"\n'
INCLUDE_ANCHOR = '#include "base/numerics/safe_conversions.h"\n'
NAMESPACE_ANCHOR = 'namespace blink {\n\n'

SCREEN_HELPER = '''namespace {\n\nbool BrowseForgeReadPositiveIntSwitch(const char* switch_name, int* value) {\n  const base::CommandLine* command_line =\n      base::CommandLine::ForCurrentProcess();\n  int parsed_value = 0;\n  if (!base::StringToInt(command_line->GetSwitchValueASCII(switch_name),\n                         &parsed_value)) {\n    return false;\n  }\n  if (parsed_value <= 0 || parsed_value > 32768) {\n    return false;\n  }\n  *value = parsed_value;\n  return true;\n}\n\nint BrowseForgeScreenSwitchOrDefault(const char* switch_name,\n                                     int default_value) {\n  int override_value = 0;\n  return BrowseForgeReadPositiveIntSwitch(switch_name, &override_value)\n             ? override_value\n             : default_value;\n}\n\nint BrowseForgeScreenAvailSwitchOrDefault(const char* avail_switch_name,\n                                          const char* screen_switch_name,\n                                          int default_value) {\n  int override_value = 0;\n  if (BrowseForgeReadPositiveIntSwitch(avail_switch_name, &override_value)) {\n    return override_value;\n  }\n  if (BrowseForgeReadPositiveIntSwitch(screen_switch_name, &override_value)) {\n    return override_value;\n  }\n  return default_value;\n}\n\n}  // namespace\n\n'''

ORIGINAL_HEIGHT = '''int Screen::height() const {\n  if (!DomWindow())\n    return 0;\n  return GetRect(/*available=*/false).height();\n}\n'''
PATCHED_HEIGHT = '''int Screen::height() const {\n  if (!DomWindow())\n    return 0;\n  return BrowseForgeScreenSwitchOrDefault(\n      "fingerprint-screen-height", GetRect(/*available=*/false).height());\n}\n'''

ORIGINAL_WIDTH = '''int Screen::width() const {\n  if (!DomWindow())\n    return 0;\n  return GetRect(/*available=*/false).width();\n}\n'''
PATCHED_WIDTH = '''int Screen::width() const {\n  if (!DomWindow())\n    return 0;\n  return BrowseForgeScreenSwitchOrDefault(\n      "fingerprint-screen-width", GetRect(/*available=*/false).width());\n}\n'''

ORIGINAL_AVAIL_HEIGHT = '''int Screen::availHeight() const {\n  if (!DomWindow())\n    return 0;\n  return GetRect(/*available=*/true).height();\n}\n'''
PATCHED_AVAIL_HEIGHT = '''int Screen::availHeight() const {\n  if (!DomWindow())\n    return 0;\n  return BrowseForgeScreenAvailSwitchOrDefault(\n      "fingerprint-screen-avail-height", "fingerprint-screen-height",\n      GetRect(/*available=*/true).height());\n}\n'''

ORIGINAL_AVAIL_WIDTH = '''int Screen::availWidth() const {\n  if (!DomWindow())\n    return 0;\n  return GetRect(/*available=*/true).width();\n}\n'''
PATCHED_AVAIL_WIDTH = '''int Screen::availWidth() const {\n  if (!DomWindow())\n    return 0;\n  return BrowseForgeScreenAvailSwitchOrDefault(\n      "fingerprint-screen-avail-width", "fingerprint-screen-width",\n      GetRect(/*available=*/true).width());\n}\n'''


def validate_chromium_src(src: Path) -> None:
    if not (src / ".git").exists():
        raise SystemExit(f"Chromium source checkout is not ready: {src}")
    if not (src / SCREEN_CC).is_file():
        raise SystemExit(f"Chromium screen source file is missing: {src / SCREEN_CC}")


def ensure_include(text: str, include: str) -> str:
    if include in text:
        return text
    if INCLUDE_ANCHOR not in text:
        raise SystemExit("screen.cc include anchor not found")
    return text.replace(INCLUDE_ANCHOR, INCLUDE_ANCHOR + include, 1)


def patch_screen(text: str) -> str:
    patched = ensure_include(text, COMMAND_LINE_INCLUDE)
    patched = ensure_include(patched, STRING_CONVERSIONS_INCLUDE)
    if "BrowseForgeReadPositiveIntSwitch" not in patched:
        if NAMESPACE_ANCHOR not in patched:
            raise SystemExit("screen.cc namespace anchor not found")
        patched = patched.replace(NAMESPACE_ANCHOR, NAMESPACE_ANCHOR + SCREEN_HELPER, 1)
    replacements = [
        (ORIGINAL_HEIGHT, PATCHED_HEIGHT, "height implementation"),
        (ORIGINAL_WIDTH, PATCHED_WIDTH, "width implementation"),
        (ORIGINAL_AVAIL_HEIGHT, PATCHED_AVAIL_HEIGHT, "availHeight implementation"),
        (ORIGINAL_AVAIL_WIDTH, PATCHED_AVAIL_WIDTH, "availWidth implementation"),
    ]
    for original, replacement, label in replacements:
        if replacement in patched:
            continue
        if original not in patched:
            raise SystemExit(f"screen.cc {label} anchor not found")
        patched = patched.replace(original, replacement, 1)
    return patched


def write_if_changed(path: Path, content: str) -> bool:
    original = path.read_text(encoding="utf-8")
    if content == original:
        return False
    path.write_text(content, encoding="utf-8")
    return True


def apply_patch(src: Path) -> list[Path]:
    validate_chromium_src(src)
    screen_path = src / SCREEN_CC
    changed = write_if_changed(screen_path, patch_screen(screen_path.read_text(encoding="utf-8")))
    return [SCREEN_CC] if changed else [SCREEN_CC]


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply BrowseForge screen fingerprint source patch")
    parser.add_argument("--chromium-src", type=Path, default=DEFAULT_CHROMIUM_SRC)
    parser.add_argument("--check", action="store_true", help="validate checkout and patch anchors without writing")
    args = parser.parse_args()

    src = args.chromium_src.resolve()
    validate_chromium_src(src)
    if args.check:
        patch_screen((src / SCREEN_CC).read_text(encoding="utf-8"))
        print(f"ready: {src / SCREEN_CC}")
        return
    for path in apply_patch(src):
        print(path.as_posix())


if __name__ == "__main__":
    main()
