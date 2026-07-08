#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_CHROMIUM_SRC = Path("/Users/chun/Projects/browser-source/browseforge-chromium/src")
WEBGL_CONTEXT_CC = Path("third_party/blink/renderer/modules/webgl/webgl_rendering_context_base.cc")

COMMAND_LINE_INCLUDE = '#include "base/command_line.h"\n'
INCLUDE_ANCHOR = '#include "base/byte_size.h"\n'
NAMESPACE_ANCHOR = 'namespace blink {\n\n'

WEBGL_HELPER = '''String BrowseForgeWebGLStringOverride(const char* switch_name) {\n  const std::string value =\n      base::CommandLine::ForCurrentProcess()->GetSwitchValueASCII(switch_name);\n  if (value.empty() || value.size() > 256) {\n    return String();\n  }\n  for (char c : value) {\n    if (c < 0x20 || c > 0x7e) {\n      return String();\n    }\n  }\n  return String::FromUTF8(value);\n}\n\n'''

ORIGINAL_RENDERER_CASE = '''    case WebGLDebugRendererInfo::kUnmaskedRendererWebgl:\n      if (ExtensionEnabled(kWebGLDebugRendererInfoName)) {\n        return WebGLAny(script_state,\n                        String(ContextGL()->GetString(GL_RENDERER)));\n      }\n'''
PATCHED_RENDERER_CASE = '''    case WebGLDebugRendererInfo::kUnmaskedRendererWebgl:\n      if (ExtensionEnabled(kWebGLDebugRendererInfoName)) {\n        String override =\n            BrowseForgeWebGLStringOverride("fingerprint-webgl-renderer");\n        if (!override.empty()) {\n          return WebGLAny(script_state, override);\n        }\n        return WebGLAny(script_state,\n                        String(ContextGL()->GetString(GL_RENDERER)));\n      }\n'''

ORIGINAL_VENDOR_CASE = '''    case WebGLDebugRendererInfo::kUnmaskedVendorWebgl:\n      if (ExtensionEnabled(kWebGLDebugRendererInfoName)) {\n        return WebGLAny(script_state,\n                        String(ContextGL()->GetString(GL_VENDOR)));\n      }\n'''
PATCHED_VENDOR_CASE = '''    case WebGLDebugRendererInfo::kUnmaskedVendorWebgl:\n      if (ExtensionEnabled(kWebGLDebugRendererInfoName)) {\n        String override =\n            BrowseForgeWebGLStringOverride("fingerprint-webgl-vendor");\n        if (!override.empty()) {\n          return WebGLAny(script_state, override);\n        }\n        return WebGLAny(script_state,\n                        String(ContextGL()->GetString(GL_VENDOR)));\n      }\n'''


def validate_chromium_src(src: Path) -> None:
    if not (src / ".git").exists():
        raise SystemExit(f"Chromium source checkout is not ready: {src}")
    if not (src / WEBGL_CONTEXT_CC).is_file():
        raise SystemExit(f"Chromium WebGL source file is missing: {src / WEBGL_CONTEXT_CC}")


def ensure_include(text: str) -> str:
    if COMMAND_LINE_INCLUDE in text:
        return text
    if INCLUDE_ANCHOR not in text:
        raise SystemExit("webgl_rendering_context_base.cc include anchor not found")
    return text.replace(INCLUDE_ANCHOR, INCLUDE_ANCHOR + COMMAND_LINE_INCLUDE, 1)


def patch_webgl_context(text: str) -> str:
    patched = ensure_include(text)
    if "BrowseForgeWebGLStringOverride" not in patched:
        if NAMESPACE_ANCHOR not in patched:
            raise SystemExit("webgl_rendering_context_base.cc namespace anchor not found")
        patched = patched.replace(NAMESPACE_ANCHOR, NAMESPACE_ANCHOR + "namespace {\n\n" + WEBGL_HELPER + "}  // namespace\n\n", 1)
    for original, replacement, label in [
        (ORIGINAL_RENDERER_CASE, PATCHED_RENDERER_CASE, "UNMASKED_RENDERER_WEBGL"),
        (ORIGINAL_VENDOR_CASE, PATCHED_VENDOR_CASE, "UNMASKED_VENDOR_WEBGL"),
    ]:
        if replacement in patched:
            continue
        if original not in patched:
            raise SystemExit(f"{label} anchor not found")
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
    path = src / WEBGL_CONTEXT_CC
    changed = write_if_changed(path, patch_webgl_context(path.read_text(encoding="utf-8")))
    return [WEBGL_CONTEXT_CC] if changed else [WEBGL_CONTEXT_CC]


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply BrowseForge WebGL vendor/renderer source patch")
    parser.add_argument("--chromium-src", type=Path, default=DEFAULT_CHROMIUM_SRC)
    parser.add_argument("--check", action="store_true", help="validate checkout and patch anchors without writing")
    args = parser.parse_args()

    src = args.chromium_src.resolve()
    validate_chromium_src(src)
    if args.check:
        patch_webgl_context((src / WEBGL_CONTEXT_CC).read_text(encoding="utf-8"))
        print(f"ready: {src / WEBGL_CONTEXT_CC}")
        return
    for path in apply_patch(src):
        print(path.as_posix())


if __name__ == "__main__":
    main()
