#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_CHROMIUM_SRC = Path("/Users/chun/Projects/browser-source/browseforge-chromium/src")
NAVIGATOR_BASE_CC = Path("third_party/blink/renderer/core/execution_context/navigator_base.cc")
NAVIGATOR_DEVICE_MEMORY_CC = Path("third_party/blink/renderer/core/frame/navigator_device_memory.cc")

COMMAND_LINE_INCLUDE = '#include "base/command_line.h"\n'
STRING_CONVERSIONS_INCLUDE = '#include "base/strings/string_number_conversions.h"\n'

BASE_INCLUDE_ANCHOR = '#include "base/feature_list.h"\n'
DEVICE_INCLUDE_ANCHOR = '#include "third_party/blink/renderer/core/frame/navigator_device_memory.h"\n'

HARDWARE_HELPER = '''\nunsigned BrowseForgeHardwareConcurrencyOverrideOrDefault(unsigned default_value) {\n  const base::CommandLine* command_line =\n      base::CommandLine::ForCurrentProcess();\n  unsigned override_value = 0;\n  if (base::StringToUint(\n          command_line->GetSwitchValueASCII("fingerprint-hardware-concurrency"),\n          &override_value) &&\n      override_value > 0 && override_value <= 128) {\n    return override_value;\n  }\n  return default_value;\n}\n'''
BASE_NAMESPACE_ANCHOR = "namespace {\n\n"

ORIGINAL_HARDWARE = '''unsigned int NavigatorBase::hardwareConcurrency() const {\n  unsigned int hardware_concurrency =\n      NavigatorConcurrentHardware::hardwareConcurrency();\n\n  probe::ApplyHardwareConcurrencyOverride(\n      probe::ToCoreProbeSink(GetExecutionContext()), hardware_concurrency);\n  return hardware_concurrency;\n}\n'''
PATCHED_HARDWARE = '''unsigned int NavigatorBase::hardwareConcurrency() const {\n  unsigned int hardware_concurrency =\n      BrowseForgeHardwareConcurrencyOverrideOrDefault(\n          NavigatorConcurrentHardware::hardwareConcurrency());\n\n  probe::ApplyHardwareConcurrencyOverride(\n      probe::ToCoreProbeSink(GetExecutionContext()), hardware_concurrency);\n  return hardware_concurrency;\n}\n'''

DEVICE_HELPER = '''\nnamespace {\n\nfloat BrowseForgeDeviceMemoryOverrideOrDefault(float default_value) {\n  const base::CommandLine* command_line =\n      base::CommandLine::ForCurrentProcess();\n  unsigned override_value = 0;\n  if (base::StringToUint(\n          command_line->GetSwitchValueASCII("fingerprint-device-memory"),\n          &override_value) &&\n      override_value > 0 && override_value <= 64) {\n    return static_cast<float>(override_value);\n  }\n  return default_value;\n}\n\n}  // namespace\n'''
DEVICE_NAMESPACE_ANCHOR = "namespace blink {\n"

ORIGINAL_DEVICE_MEMORY = '''float NavigatorDeviceMemory::deviceMemory() const {\n  return ApproximatedDeviceMemory::GetApproximatedDeviceMemory();\n}\n'''
PATCHED_DEVICE_MEMORY = '''float NavigatorDeviceMemory::deviceMemory() const {\n  return BrowseForgeDeviceMemoryOverrideOrDefault(\n      ApproximatedDeviceMemory::GetApproximatedDeviceMemory());\n}\n'''


def validate_chromium_src(src: Path) -> None:
    if not (src / ".git").exists():
        raise SystemExit(f"Chromium source checkout is not ready: {src}")
    for rel in (NAVIGATOR_BASE_CC, NAVIGATOR_DEVICE_MEMORY_CC):
        if not (src / rel).is_file():
            raise SystemExit(f"Chromium source file is missing: {src / rel}")


def ensure_include(text: str, anchor: str, include: str, label: str) -> str:
    if include in text:
        return text
    if anchor not in text:
        raise SystemExit(f"{label} include anchor not found")
    return text.replace(anchor, anchor + include, 1)


def patch_hardware_concurrency(text: str) -> str:
    patched = ensure_include(text, BASE_INCLUDE_ANCHOR, COMMAND_LINE_INCLUDE, "navigator_base.cc")
    patched = ensure_include(patched, COMMAND_LINE_INCLUDE, STRING_CONVERSIONS_INCLUDE, "navigator_base.cc")
    if "BrowseForgeHardwareConcurrencyOverrideOrDefault" not in patched:
        if BASE_NAMESPACE_ANCHOR not in patched:
            raise SystemExit("navigator_base.cc namespace anchor not found")
        patched = patched.replace(BASE_NAMESPACE_ANCHOR, BASE_NAMESPACE_ANCHOR + HARDWARE_HELPER + "\n", 1)
    if PATCHED_HARDWARE in patched:
        return patched
    if ORIGINAL_HARDWARE not in patched:
        raise SystemExit("hardwareConcurrency implementation anchor not found")
    return patched.replace(ORIGINAL_HARDWARE, PATCHED_HARDWARE, 1)


def patch_device_memory(text: str) -> str:
    patched = ensure_include(text, DEVICE_INCLUDE_ANCHOR, COMMAND_LINE_INCLUDE + STRING_CONVERSIONS_INCLUDE, "navigator_device_memory.cc")
    if "BrowseForgeDeviceMemoryOverrideOrDefault" not in patched:
        if DEVICE_NAMESPACE_ANCHOR not in patched:
            raise SystemExit("navigator_device_memory.cc namespace anchor not found")
        patched = patched.replace(DEVICE_NAMESPACE_ANCHOR, DEVICE_HELPER + "\n" + DEVICE_NAMESPACE_ANCHOR, 1)
    if PATCHED_DEVICE_MEMORY in patched:
        return patched
    if ORIGINAL_DEVICE_MEMORY not in patched:
        raise SystemExit("deviceMemory implementation anchor not found")
    return patched.replace(ORIGINAL_DEVICE_MEMORY, PATCHED_DEVICE_MEMORY, 1)


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
    device_path = src / NAVIGATOR_DEVICE_MEMORY_CC
    if write_if_changed(base_path, patch_hardware_concurrency(base_path.read_text(encoding="utf-8"))):
        changed.append(NAVIGATOR_BASE_CC)
    if write_if_changed(device_path, patch_device_memory(device_path.read_text(encoding="utf-8"))):
        changed.append(NAVIGATOR_DEVICE_MEMORY_CC)
    return changed or [NAVIGATOR_BASE_CC, NAVIGATOR_DEVICE_MEMORY_CC]


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply BrowseForge hardware fingerprint source patches")
    parser.add_argument("--chromium-src", type=Path, default=DEFAULT_CHROMIUM_SRC)
    parser.add_argument("--check", action="store_true", help="validate checkout and patch anchors without writing")
    args = parser.parse_args()

    src = args.chromium_src.resolve()
    validate_chromium_src(src)
    if args.check:
        patch_hardware_concurrency((src / NAVIGATOR_BASE_CC).read_text(encoding="utf-8"))
        patch_device_memory((src / NAVIGATOR_DEVICE_MEMORY_CC).read_text(encoding="utf-8"))
        print(f"ready: {src / NAVIGATOR_BASE_CC}")
        print(f"ready: {src / NAVIGATOR_DEVICE_MEMORY_CC}")
        return
    for path in apply_patch(src):
        print(path.as_posix())


if __name__ == "__main__":
    main()
