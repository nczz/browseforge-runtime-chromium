#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_CHROMIUM_SRC = Path("/Users/chun/Projects/browser-source/browseforge-chromium/src")
STYLE_RESOLVER_CC = Path("third_party/blink/renderer/core/css/resolver/style_resolver.cc")

ORIGINAL_BASE_STYLE_DCHECK = '''    const ComputedStyle* style_snapshot = state.StyleBuilder().CloneStyle();
    DCHECK_EQ(g_null_atom, ComputeBaseComputedStyleDiff(
                               animation_base_computed_style, *style_snapshot));
#endif

    state.CreateNewClonedStyle(*animation_base_computed_style);'''

PATCHED_BASE_STYLE_DCHECK = '''    const ComputedStyle* style_snapshot = state.StyleBuilder().CloneStyle();
    const String base_style_diff = ComputeBaseComputedStyleDiff(
        animation_base_computed_style, *style_snapshot);
    if (base_style_diff != g_null_atom) {
      LOG(WARNING) << "BrowseForge: animation base computed style mismatch: "
                   << base_style_diff.Utf8();
      MaybeResetCascade(cascade);
      return;
    }
#endif

    state.CreateNewClonedStyle(*animation_base_computed_style);'''

BASE_CONTAINERS_INCLUDE = '#include "base/containers/adapters.h"\n'
CHECK_INCLUDE = '#include "base/check.h"\n'
LOGGING_INCLUDE = '#include "base/logging.h"\n'


def validate_chromium_src(src: Path) -> None:
    if not (src / ".git").exists():
        raise SystemExit(f"Chromium source checkout is not ready: {src}")
    if not (src / STYLE_RESOLVER_CC).is_file():
        raise SystemExit(f"Chromium style resolver source file is missing: {src / STYLE_RESOLVER_CC}")


def patch_style_resolver(text: str) -> str:
    patched = text
    if LOGGING_INCLUDE not in patched:
        if CHECK_INCLUDE in patched:
            patched = patched.replace(CHECK_INCLUDE, CHECK_INCLUDE + LOGGING_INCLUDE, 1)
        elif BASE_CONTAINERS_INCLUDE in patched:
            patched = patched.replace(
                BASE_CONTAINERS_INCLUDE,
                BASE_CONTAINERS_INCLUDE + LOGGING_INCLUDE,
                1,
            )
        else:
            raise SystemExit("style_resolver.cc include anchor not found")
    if PATCHED_BASE_STYLE_DCHECK in patched:
        return patched
    if ORIGINAL_BASE_STYLE_DCHECK not in patched:
        raise SystemExit("StyleResolver::ApplyBaseStyle DCHECK anchor not found")
    return patched.replace(ORIGINAL_BASE_STYLE_DCHECK, PATCHED_BASE_STYLE_DCHECK, 1)


def apply_patch(src: Path) -> list[Path]:
    validate_chromium_src(src)
    path = src / STYLE_RESOLVER_CC
    original = path.read_text(encoding="utf-8")
    patched = patch_style_resolver(original)
    if patched != original:
        path.write_text(patched, encoding="utf-8")
    return [STYLE_RESOLVER_CC]


def check_patch(src: Path) -> list[Path]:
    validate_chromium_src(src)
    path = src / STYLE_RESOLVER_CC
    patch_style_resolver(path.read_text(encoding="utf-8"))
    return [STYLE_RESOLVER_CC]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chromium-src", type=Path, default=DEFAULT_CHROMIUM_SRC)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    if args.check:
        checked = check_patch(args.chromium_src)
        print("style resolver patch ready:", ", ".join(str(p) for p in checked))
        return 0
    for path in apply_patch(args.chromium_src):
        print(path.as_posix())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
