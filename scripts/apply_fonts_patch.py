#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_CHROMIUM_SRC = Path("/Users/chun/Projects/browser-source/browseforge-chromium/src")
FONT_FACE_SET_CC = Path("third_party/blink/renderer/core/css/font_face_set.cc")

COMMAND_LINE_INCLUDE = '#include "base/command_line.h"\n'
INCLUDE_ANCHOR = '#include "base/task/single_thread_task_runner.h"\n'
NAMESPACE_ANCHOR = 'namespace blink {\n\n'

FONTS_HELPER = '''namespace {

bool BrowseForgeFontFamilyAllowed(const String& font_string) {
  const std::string fonts = base::CommandLine::ForCurrentProcess()
                                ->GetSwitchValueASCII("fingerprint-fonts-list");
  if (fonts.empty() || fonts.size() > 8192) {
    return false;
  }
  const std::string query = font_string.Utf8();
  if (query.empty()) {
    return false;
  }
  size_t start = 0;
  while (start <= fonts.size()) {
    size_t end = fonts.find('|', start);
    const std::string family = fonts.substr(
        start, end == std::string::npos ? std::string::npos : end - start);
    if (!family.empty() && family.size() <= 128) {
      bool printable = true;
      for (char c : family) {
        if (c < 0x20 || c > 0x7e || c == '|') {
          printable = false;
          break;
        }
      }
      if (printable && query.find(family) != std::string::npos) {
        return true;
      }
    }
    if (end == std::string::npos) {
      break;
    }
    start = end + 1;
  }
  return false;
}

}  // namespace

'''

ORIGINAL_CHECK_PREFIX = '''  const Font* font = ResolveFontStyle(font_string);
  if (!font) {
    exception_state.ThrowDOMException(
        DOMExceptionCode::kSyntaxError,
        StrCat({"Could not resolve '", font_string, "' as a font."}));
    return false;
  }

  FontSelector* font_selector = GetFontSelector();
'''
PATCHED_CHECK_PREFIX = '''  const Font* font = ResolveFontStyle(font_string);
  if (!font) {
    exception_state.ThrowDOMException(
        DOMExceptionCode::kSyntaxError,
        StrCat({"Could not resolve '", font_string, "' as a font."}));
    return false;
  }
  if (BrowseForgeFontFamilyAllowed(font_string)) {
    return true;
  }

  FontSelector* font_selector = GetFontSelector();
'''


def validate_chromium_src(src: Path) -> None:
    if not (src / ".git").exists():
        raise SystemExit(f"Chromium source checkout is not ready: {src}")
    if not (src / FONT_FACE_SET_CC).is_file():
        raise SystemExit(f"Chromium FontFaceSet source file is missing: {src / FONT_FACE_SET_CC}")


def ensure_include(text: str) -> str:
    if COMMAND_LINE_INCLUDE in text:
        return text
    if INCLUDE_ANCHOR not in text:
        raise SystemExit("font_face_set.cc include anchor not found")
    return text.replace(INCLUDE_ANCHOR, INCLUDE_ANCHOR + COMMAND_LINE_INCLUDE, 1)


def patch_font_face_set(text: str) -> str:
    patched = ensure_include(text)
    if "BrowseForgeFontFamilyAllowed" not in patched:
        if NAMESPACE_ANCHOR not in patched:
            raise SystemExit("font_face_set.cc namespace anchor not found")
        patched = patched.replace(NAMESPACE_ANCHOR, NAMESPACE_ANCHOR + FONTS_HELPER, 1)
    if PATCHED_CHECK_PREFIX in patched:
        return patched
    if ORIGINAL_CHECK_PREFIX not in patched:
        raise SystemExit("FontFaceSet::check implementation anchor not found")
    return patched.replace(ORIGINAL_CHECK_PREFIX, PATCHED_CHECK_PREFIX, 1)


def write_if_changed(path: Path, content: str) -> bool:
    original = path.read_text(encoding="utf-8")
    if content == original:
        return False
    path.write_text(content, encoding="utf-8")
    return True


def apply_patch(src: Path) -> list[Path]:
    validate_chromium_src(src)
    path = src / FONT_FACE_SET_CC
    write_if_changed(path, patch_font_face_set(path.read_text(encoding="utf-8")))
    return [FONT_FACE_SET_CC]


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply BrowseForge FontFaceSet font availability source patch")
    parser.add_argument("--chromium-src", type=Path, default=DEFAULT_CHROMIUM_SRC)
    parser.add_argument("--check", action="store_true", help="validate checkout and patch anchors without writing")
    args = parser.parse_args()

    src = args.chromium_src.resolve()
    validate_chromium_src(src)
    if args.check:
        patch_font_face_set((src / FONT_FACE_SET_CC).read_text(encoding="utf-8"))
        print(f"ready: {src / FONT_FACE_SET_CC}")
        return
    for path in apply_patch(src):
        print(path.as_posix())


if __name__ == "__main__":
    main()
