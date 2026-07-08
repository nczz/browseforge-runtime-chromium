#!/usr/bin/env python3
from __future__ import annotations

import argparse
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCAFFOLD = ROOT / "browser" / "stealth"
DEFAULT_CHROMIUM_SRC = Path("/Users/chun/Projects/browser-source/browseforge-chromium/src")


def validate_chromium_src(src: Path) -> None:
    if not (src / ".git").exists():
        raise SystemExit(f"Chromium source checkout is not ready: {src}")
    if src.resolve().is_relative_to(ROOT.resolve()):
        raise SystemExit("Refusing to copy Chromium patch scaffold inside the runtime repository")


def apply_scaffold(src: Path) -> list[Path]:
    validate_chromium_src(src)
    dest = src / "browseforge" / "stealth"
    dest.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SCAFFOLD, dest, dirs_exist_ok=True)
    copied = sorted(path.relative_to(src) for path in dest.rglob("*") if path.is_file())
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
        print(f"ready: {src}")
        return
    for path in apply_scaffold(src):
        print(path.as_posix())


if __name__ == "__main__":
    main()
