#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAFFOLD = ROOT / "browser" / "stealth"
DEFAULT_CHROMIUM_SRC = Path("/Users/chun/Projects/browser-source/browseforge-chromium/src")
GN_ALL_DEP = '      "//browseforge/stealth",'
GN_ALL_ANCHOR = '      "//url:url_unittests",'



def validate_chromium_src(src: Path) -> None:
    if not (src / ".git").exists():
        raise SystemExit(f"Chromium source checkout is not ready: {src}")
    if src.resolve().is_relative_to(ROOT.resolve()):
        raise SystemExit("Refusing to copy Chromium patch scaffold inside the runtime repository")


def patch_root_build(src: Path) -> Path:
    root_build = src / "BUILD.gn"
    if not root_build.is_file():
        raise SystemExit(f"Chromium root BUILD.gn is missing: {root_build}")
    text = root_build.read_text(encoding="utf-8")
    if GN_ALL_DEP in text:
        return root_build
    if GN_ALL_ANCHOR not in text:
        raise SystemExit("Chromium root BUILD.gn gn_all deps anchor not found")
    root_build.write_text(text.replace(GN_ALL_ANCHOR, f"{GN_ALL_DEP}\n{GN_ALL_ANCHOR}", 1), encoding="utf-8")
    return root_build


def scaffold_file_paths() -> list[Path]:
    return sorted(path.relative_to(SCAFFOLD) for path in SCAFFOLD.rglob("*") if path.is_file())


def verify_scaffold_applied(src: Path) -> None:
    validate_chromium_src(src)
    dest = src / "browseforge" / "stealth"
    missing = [path.as_posix() for path in scaffold_file_paths() if not (dest / path).is_file()]
    if missing:
        raise SystemExit(f"BrowseForge stealth scaffold is not fully applied; missing files: {missing}")
    root_build = src / "BUILD.gn"
    if not root_build.is_file():
        raise SystemExit(f"Chromium root BUILD.gn is missing: {root_build}")
    if GN_ALL_DEP not in root_build.read_text(encoding="utf-8"):
        raise SystemExit("Chromium root BUILD.gn does not include //browseforge/stealth in gn_all deps")


def apply_scaffold(src: Path) -> list[Path]:
    validate_chromium_src(src)
    dest = src / "browseforge" / "stealth"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SCAFFOLD, dest, dirs_exist_ok=True)
    copied = sorted(path.relative_to(src) for path in dest.rglob("*") if path.is_file())
    patched = patch_root_build(src).relative_to(src)
    copied = sorted([*copied, patched])
    if not copied:
        raise SystemExit("No stealth scaffold files copied")
    return copied


def main() -> None:
    parser = argparse.ArgumentParser(description="Copy BrowseForge stealth scaffold into a Chromium checkout")
    parser.add_argument("--chromium-src", type=Path, default=DEFAULT_CHROMIUM_SRC)
    parser.add_argument("--check", action="store_true", help="only validate that the checkout is ready")
    args = parser.parse_args()

    src = args.chromium_src.resolve()
    validate_chromium_src(src)
    if args.check:
        verify_scaffold_applied(src)
        print(f"ready: {src}")
        return
    for path in apply_scaffold(src):
        print(path.as_posix())


if __name__ == "__main__":
    main()
