#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_CHROMIUM_SRC = Path("/Users/chun/Projects/browser-source/browseforge-chromium/src")
DOM_PLUGIN_ARRAY_CC = Path("third_party/blink/renderer/modules/plugins/dom_plugin_array.cc")

COMMAND_LINE_INCLUDE = '#include "base/command_line.h"\n'
INCLUDE_ANCHOR = '#include "third_party/blink/public/common/features.h"\n'
NAMESPACE_ANCHOR = "namespace {\n"

PLUGINS_HELPER = '''namespace {\n\nbool BrowseForgePluginsPDFOverrideOrDefault(bool default_value) {\n  std::string mode = base::CommandLine::ForCurrentProcess()->GetSwitchValueASCII(\n      "fingerprint-plugins-pdf");\n  if (mode == "enabled" || mode == "true" || mode == "1") {\n    return true;\n  }\n  if (mode == "disabled" || mode == "false" || mode == "0") {\n    return false;\n  }\n  return default_value;\n}\n\n'''

ORIGINAL_PDF_AVAILABLE = '''bool DOMPluginArray::IsPdfViewerAvailable() {\n  auto* data = GetPluginData();\n  if (!data)\n    return false;\n  for (const Member<MimeClassInfo>& mime_info : data->Mimes()) {\n    if (mime_info->Type() == "application/pdf")\n      return true;\n  }\n  return false;\n}\n'''
PATCHED_PDF_AVAILABLE = '''bool DOMPluginArray::IsPdfViewerAvailable() {\n  bool pdf_available = false;\n  if (auto* data = GetPluginData()) {\n    for (const Member<MimeClassInfo>& mime_info : data->Mimes()) {\n      if (mime_info->Type() == "application/pdf") {\n        pdf_available = true;\n        break;\n      }\n    }\n  }\n  return BrowseForgePluginsPDFOverrideOrDefault(pdf_available);\n}\n'''


def validate_chromium_src(src: Path) -> None:
    if not (src / ".git").exists():
        raise SystemExit(f"Chromium source checkout is not ready: {src}")
    if not (src / DOM_PLUGIN_ARRAY_CC).is_file():
        raise SystemExit(f"Chromium plugins source file is missing: {src / DOM_PLUGIN_ARRAY_CC}")


def ensure_include(text: str) -> str:
    if COMMAND_LINE_INCLUDE in text:
        return text
    if INCLUDE_ANCHOR not in text:
        raise SystemExit("dom_plugin_array.cc include anchor not found")
    return text.replace(INCLUDE_ANCHOR, COMMAND_LINE_INCLUDE + INCLUDE_ANCHOR, 1)


def patch_plugins(text: str) -> str:
    patched = ensure_include(text)
    if "BrowseForgePluginsPDFOverrideOrDefault" not in patched:
        if NAMESPACE_ANCHOR not in patched:
            raise SystemExit("dom_plugin_array.cc namespace anchor not found")
        patched = patched.replace(NAMESPACE_ANCHOR, PLUGINS_HELPER, 1)
    if PATCHED_PDF_AVAILABLE in patched:
        return patched
    if ORIGINAL_PDF_AVAILABLE not in patched:
        raise SystemExit("DOMPluginArray::IsPdfViewerAvailable anchor not found")
    return patched.replace(ORIGINAL_PDF_AVAILABLE, PATCHED_PDF_AVAILABLE, 1)


def write_if_changed(path: Path, content: str) -> bool:
    original = path.read_text(encoding="utf-8")
    if content == original:
        return False
    path.write_text(content, encoding="utf-8")
    return True


def apply_patch(src: Path) -> list[Path]:
    validate_chromium_src(src)
    path = src / DOM_PLUGIN_ARRAY_CC
    write_if_changed(path, patch_plugins(path.read_text(encoding="utf-8")))
    return [DOM_PLUGIN_ARRAY_CC]


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply BrowseForge plugins/native PDF viewer source patch")
    parser.add_argument("--chromium-src", type=Path, default=DEFAULT_CHROMIUM_SRC)
    parser.add_argument("--check", action="store_true", help="validate checkout and patch anchors without writing")
    args = parser.parse_args()

    src = args.chromium_src.resolve()
    validate_chromium_src(src)
    if args.check:
        patch_plugins((src / DOM_PLUGIN_ARRAY_CC).read_text(encoding="utf-8"))
        print(f"ready: {src / DOM_PLUGIN_ARRAY_CC}")
        return
    for path in apply_patch(src):
        print(path.as_posix())


if __name__ == "__main__":
    main()
