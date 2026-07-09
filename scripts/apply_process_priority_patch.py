#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_CHROMIUM_SRC = Path("/Users/chun/Projects/browser-source/browseforge-chromium/src")
PROCESS_LINUX_CC = Path("base/process/process_linux.cc")

LOGGING_INCLUDE = '#include "base/logging.h"\n'
CHECK_INCLUDE = '#include "base/check.h"\n'

ORIGINAL_SET_PRIORITY = '''  int result =
      setpriority(PRIO_PROCESS, static_cast<id_t>(process_), priority_value);
  DPCHECK(result == 0);
  return result == 0;
}'''

PATCHED_SET_PRIORITY = '''  int result =
      setpriority(PRIO_PROCESS, static_cast<id_t>(process_), priority_value);
  if (result != 0) {
    PLOG(WARNING) << "BrowseForge: setpriority failed";
  }
  return result == 0;
}'''


def validate_chromium_src(src: Path) -> None:
    if not (src / ".git").exists():
        raise SystemExit(f"Chromium source checkout is not ready: {src}")
    if not (src / PROCESS_LINUX_CC).is_file():
        raise SystemExit(f"Chromium process source file is missing: {src / PROCESS_LINUX_CC}")


def patch_process_linux(text: str) -> str:
    patched = text
    if LOGGING_INCLUDE not in patched:
        if CHECK_INCLUDE not in patched:
            raise SystemExit("base/process/process_linux.cc include anchor not found")
        patched = patched.replace(CHECK_INCLUDE, CHECK_INCLUDE + LOGGING_INCLUDE, 1)
    if PATCHED_SET_PRIORITY in patched:
        return patched
    if ORIGINAL_SET_PRIORITY not in patched:
        raise SystemExit("base::Process::SetPriority anchor not found")
    return patched.replace(ORIGINAL_SET_PRIORITY, PATCHED_SET_PRIORITY, 1)


def apply_patch(src: Path) -> list[Path]:
    validate_chromium_src(src)
    path = src / PROCESS_LINUX_CC
    original = path.read_text(encoding="utf-8")
    patched = patch_process_linux(original)
    if patched != original:
        path.write_text(patched, encoding="utf-8")
    return [PROCESS_LINUX_CC]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chromium-src", type=Path, default=DEFAULT_CHROMIUM_SRC)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    changed = apply_patch(args.chromium_src)
    if args.check:
        print("process priority patch ready:", ", ".join(str(p) for p in changed))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
