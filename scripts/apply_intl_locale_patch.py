#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_CHROMIUM_SRC = Path("/Users/chun/Projects/browser-source/browseforge-chromium/src")
ISOLATE_CC = Path("v8/src/execution/isolate.cc")

OLD = '''const std::string& Isolate::DefaultLocale() {
  if (default_locale_.empty()) {
    icu::Locale default_locale;
    // Translate ICU's fallback locale to a well-known locale.
    if (strcmp(default_locale.getName(), "en_US_POSIX") == 0 ||
        strcmp(default_locale.getName(), "c") == 0) {
      set_default_locale("en-US");
    } else {
      // Set the locale
      set_default_locale(default_locale.isBogus()
                             ? "und"
                             : Intl::ToLanguageTag(default_locale).FromJust());
    }
    DCHECK(!default_locale_.empty());
  }
  return default_locale_;
}
'''

NEW = '''const std::string& Isolate::DefaultLocale() {
  if (default_locale_.empty()) {
    if (const char* browseforge_locale = getenv("BROWSEFORGE_INTL_LOCALE");
        browseforge_locale && browseforge_locale[0] != '\\0') {
      set_default_locale(browseforge_locale);
    } else {
      icu::Locale default_locale;
      // Translate ICU's fallback locale to a well-known locale.
      if (strcmp(default_locale.getName(), "en_US_POSIX") == 0 ||
          strcmp(default_locale.getName(), "c") == 0) {
        set_default_locale("en-US");
      } else {
        // Set the locale
        set_default_locale(default_locale.isBogus()
                               ? "und"
                               : Intl::ToLanguageTag(default_locale).FromJust());
      }
    }
    DCHECK(!default_locale_.empty());
  }
  return default_locale_;
}
'''


def validate_chromium_src(src: Path) -> None:
    path = src / ISOLATE_CC
    if not path.is_file():
        raise SystemExit(f"missing {path}")


def patch_isolate(text: str) -> str:
    if NEW in text:
        return text
    if OLD not in text:
        raise SystemExit("isolate.cc anchor not found; Chromium source changed")
    return text.replace(OLD, NEW, 1)


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply BrowseForge V8 Intl default locale source patch")
    parser.add_argument("--chromium-src", type=Path, default=DEFAULT_CHROMIUM_SRC)
    parser.add_argument("--check", action="store_true", help="validate checkout and patch anchors without writing")
    args = parser.parse_args()

    src = args.chromium_src.resolve()
    validate_chromium_src(src)
    path = src / ISOLATE_CC
    text = path.read_text(encoding="utf-8")
    patched = patch_isolate(text)
    if args.check:
        print(f"ready: {path}")
        return
    if patched != text:
        path.write_text(patched, encoding="utf-8")
    print(path.as_posix())


if __name__ == "__main__":
    main()
