#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_CHROMIUM_SRC = Path("/Users/chun/Projects/browser-source/browseforge-chromium/src")
RENDER_PROCESS_HOST_IMPL_CC = Path("content/browser/renderer_host/render_process_host_impl.cc")

ANCHOR = "  static const char* const kSwitchNames[] = {\n"
BROWSEFORGE_SWITCHES = [
    "browseforge-stealth-config",
    "browseforge-stealth-mode",
    "fingerprint",
    "fingerprint-accept-language",
    "fingerprint-audio-noise",
    "fingerprint-canvas-noise",
    "fingerprint-device-memory",
    "fingerprint-fonts-dir",
    "fingerprint-fonts-list",
    "fingerprint-hardware-concurrency",
    "fingerprint-locale",
    "fingerprint-native-config",
    "fingerprint-native-mode",
    "fingerprint-platform",
    "fingerprint-plugins-pdf",
    "fingerprint-screen-avail-height",
    "fingerprint-screen-avail-width",
    "fingerprint-screen-height",
    "fingerprint-screen-device-scale-factor",
    "fingerprint-screen-width",
    "fingerprint-storage-quota",
    "fingerprint-timezone",
    "fingerprint-ua-architecture",
    "fingerprint-ua-bitness",
    "fingerprint-ua-full-version",
    "fingerprint-ua-mobile",
    "fingerprint-ua-model",
    "fingerprint-ua-platform",
    "fingerprint-ua-platform-version",
    "fingerprint-ua-wow64",
    "fingerprint-user-agent",
    "fingerprint-webrtc-ip",
    "fingerprint-webgl-renderer",
    "fingerprint-webgl-vendor",
]
BROWSEFORGE_SWITCH_BLOCK = (
    "      // BrowseForge fingerprint and stealth switches are intentionally\n"
    "      // browser-owned public contract knobs. Blink-side patches read them in\n"
    "      // renderer processes, so they must survive Chromium's child command-line\n"
    "      // allowlist.\n"
    + "".join(f'      "{switch}",\n' for switch in BROWSEFORGE_SWITCHES)
)
BROWSEFORGE_SWITCH_SET = set(BROWSEFORGE_SWITCHES)
BROWSEFORGE_BLOCK_COMMENT_LINES = {
    line.strip()
    for line in BROWSEFORGE_SWITCH_BLOCK.splitlines()
    if line.strip().startswith("//")
}


def browseforge_switch_name(line: str) -> str | None:
    stripped = line.strip()
    if not stripped.startswith('"'):
        return None
    end = stripped.find('"', 1)
    if end == -1:
        return None
    name = stripped[1:end]
    return name if name in BROWSEFORGE_SWITCH_SET else None


def is_browseforge_block_line(line: str) -> bool:
    stripped = line.strip()
    return stripped in BROWSEFORGE_BLOCK_COMMENT_LINES or browseforge_switch_name(line) is not None


def strip_leading_browseforge_switch_block(text: str) -> str:
    lines = text.splitlines(keepends=True)
    first_non_browseforge = 0
    while first_non_browseforge < len(lines) and is_browseforge_block_line(lines[first_non_browseforge]):
        first_non_browseforge += 1
    return "".join(lines[first_non_browseforge:])


def validate_chromium_src(src: Path) -> None:
    if not (src / ".git").exists():
        raise SystemExit(f"Chromium source checkout is not ready: {src}")
    if not (src / RENDER_PROCESS_HOST_IMPL_CC).is_file():
        raise SystemExit(f"Chromium renderer host source file is missing: {src / RENDER_PROCESS_HOST_IMPL_CC}")


def missing_browseforge_switches(text: str) -> list[str]:
    return [switch for switch in BROWSEFORGE_SWITCHES if f'"{switch}"' not in text]


def patch_switch_propagation(text: str) -> str:
    if ANCHOR not in text:
        raise SystemExit("RenderProcessHostImpl renderer switch allowlist anchor not found")
    before, after = text.split(ANCHOR, 1)
    patched = before + ANCHOR + BROWSEFORGE_SWITCH_BLOCK + strip_leading_browseforge_switch_block(after)
    return patched


def apply_patch(src: Path) -> list[Path]:
    validate_chromium_src(src)
    path = src / RENDER_PROCESS_HOST_IMPL_CC
    original = path.read_text(encoding="utf-8")
    patched = patch_switch_propagation(original)
    if patched != original:
        path.write_text(patched, encoding="utf-8")
    return [RENDER_PROCESS_HOST_IMPL_CC]

def check_patch(src: Path) -> list[Path]:
    validate_chromium_src(src)
    path = src / RENDER_PROCESS_HOST_IMPL_CC
    patch_switch_propagation(path.read_text(encoding="utf-8"))
    return [RENDER_PROCESS_HOST_IMPL_CC]



def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chromium-src", type=Path, default=DEFAULT_CHROMIUM_SRC)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        checked = check_patch(args.chromium_src.resolve())
        print("switch propagation patch ready:", ", ".join(str(p) for p in checked))
        return 0
    for path in apply_patch(args.chromium_src.resolve()):
        print(path.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
