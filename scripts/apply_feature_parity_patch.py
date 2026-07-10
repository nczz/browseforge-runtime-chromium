#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_CHROMIUM_SRC = Path("/Users/chun/Projects/browser-source/browseforge-chromium/src")
RUNTIME_FEATURES_JSON5 = Path("third_party/blink/renderer/platform/runtime_enabled_features.json5")

CONTACTS_ORIGINAL = '''    {
      name: "ContactsManager",
      status:  {"Android": "stable", "default": "test"},
    },
    {
      name: "ContactsManagerExtraProperties",
      status:  {"Android": "stable", "default": "test"},
    },
'''
CONTACTS_PATCHED = '''    {
      name: "ContactsManager",
      status: "stable",
    },
    {
      name: "ContactsManagerExtraProperties",
      status: "stable",
    },
'''

CONTENT_INDEX_ORIGINAL = '''    {
      name: "ContentIndex",
      status:  {"Android": "stable", "default": "experimental"},
    },
'''
CONTENT_INDEX_PATCHED = '''    {
      name: "ContentIndex",
      status: "stable",
    },
'''

NETINFO_ORIGINAL = '''    {
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
'''
NETINFO_PATCHED = '''    {
      name: "NetInfoDownlinkMax",
      public: true,
      // BrowseForge enables this desktop parity surface to avoid Chrome feature
      // inventory gaps when a profile claims a modern desktop Chrome persona.
      status: "stable",
      base_feature: "none",
    },
'''

SERIAL_PORT_CONNECTED_ORIGINAL = '''    {
      name: "SerialPortConnected",
      status: {"Android": "", "default": "experimental"},
      base_feature: "none",
    },
'''
SERIAL_PORT_CONNECTED_PATCHED = '''    {
      name: "SerialPortConnected",
      // BrowseForge keeps desktop serial feature inventory coherent with
      // navigator.serial availability without requiring device access.
      status: "stable",
      base_feature: "none",
    },
'''


def validate_chromium_src(src: Path) -> None:
    if not (src / ".git").exists():
        raise SystemExit(f"Chromium source checkout is not ready: {src}")
    if not (src / RUNTIME_FEATURES_JSON5).is_file():
        raise SystemExit(f"Chromium runtime feature file is missing: {src / RUNTIME_FEATURES_JSON5}")


def replace_once(text: str, original: str, patched: str, label: str) -> str:
    if patched in text:
        return text
    if original not in text:
        raise SystemExit(f"{label} runtime feature anchor not found")
    return text.replace(original, patched, 1)


def patch_runtime_features(text: str) -> str:
    patched = replace_once(text, CONTACTS_ORIGINAL, CONTACTS_PATCHED, "ContactsManager")
    patched = replace_once(patched, CONTENT_INDEX_ORIGINAL, CONTENT_INDEX_PATCHED, "ContentIndex")
    patched = replace_once(patched, NETINFO_ORIGINAL, NETINFO_PATCHED, "NetInfoDownlinkMax")
    patched = replace_once(
        patched,
        SERIAL_PORT_CONNECTED_ORIGINAL,
        SERIAL_PORT_CONNECTED_PATCHED,
        "SerialPortConnected",
    )
    return patched


def write_if_changed(path: Path, content: str) -> bool:
    original = path.read_text(encoding="utf-8")
    if content == original:
        return False
    path.write_text(content, encoding="utf-8")
    return True


def apply_patch(src: Path) -> list[Path]:
    validate_chromium_src(src)
    path = src / RUNTIME_FEATURES_JSON5
    write_if_changed(path, patch_runtime_features(path.read_text(encoding="utf-8")))
    return [RUNTIME_FEATURES_JSON5]


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply BrowseForge Chromium feature parity source patch")
    parser.add_argument("--chromium-src", type=Path, default=DEFAULT_CHROMIUM_SRC)
    parser.add_argument("--check", action="store_true", help="validate checkout and patch anchors without writing")
    args = parser.parse_args()

    src = args.chromium_src.resolve()
    validate_chromium_src(src)
    if args.check:
        patch_runtime_features((src / RUNTIME_FEATURES_JSON5).read_text(encoding="utf-8"))
        print(f"ready: {src / RUNTIME_FEATURES_JSON5}")
        return
    for path in apply_patch(src):
        print(path.as_posix())


if __name__ == "__main__":
    main()
