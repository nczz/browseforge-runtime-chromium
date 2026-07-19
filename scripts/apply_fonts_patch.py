#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_CHROMIUM_SRC = Path("/Users/chun/Projects/browser-source/browseforge-chromium/src")
FONT_FACE_SET_CC = Path("third_party/blink/renderer/core/css/font_face_set.cc")
CSS_FONT_SELECTOR_CC = Path("third_party/blink/renderer/core/css/css_font_selector.cc")
CSS_FONT_FAMILY_VALUE_CC = Path("third_party/blink/renderer/core/css/css_font_family_value.cc")

UNORDERED_SET_INCLUDE = '#include <unordered_set>\n'
COMMAND_LINE_INCLUDE = '#include "base/command_line.h"\n'
INCLUDE_ANCHOR = '#include "base/task/single_thread_task_runner.h"\n'
NAMESPACE_ANCHOR = 'namespace blink {\n\n'

FONTS_HELPER = '''namespace {

enum class BrowseForgeFontAllowlistDecision {
  kNoAllowlist,
  kAllowed,
  kDenied,
};

const std::unordered_set<std::string>& BrowseForgeFontAllowlistFamilies() {
  static const std::unordered_set<std::string>* families = [] {
    auto* parsed = new std::unordered_set<std::string>();
    const std::string fonts = base::CommandLine::ForCurrentProcess()
                                  ->GetSwitchValueASCII("fingerprint-fonts-list");
    if (fonts.empty() || fonts.size() > 8192) {
      return parsed;
    }
    size_t start = 0;
    while (start <= fonts.size()) {
      size_t end = fonts.find('|', start);
      const size_t length =
          end == std::string::npos ? fonts.size() - start : end - start;
      bool printable = length > 0 && length <= 128;
      for (size_t i = start; printable && i < start + length; ++i) {
        const char c = fonts[i];
        if (c < 0x20 || c > 0x7e || c == '|') {
          printable = false;
        }
      }
      if (printable) {
        parsed->insert(fonts.substr(start, length));
      }
      if (end == std::string::npos) {
        break;
      }
      start = end + 1;
    }
    return parsed;
  }();
  return *families;
}

std::string BrowseForgeTrimFontFamily(std::string family) {
  size_t start = 0;
  while (start < family.size() &&
         (family[start] == ' ' || family[start] == '\\t' ||
          family[start] == '\\n' || family[start] == '\\r')) {
    ++start;
  }
  size_t end = family.size();
  while (end > start &&
         (family[end - 1] == ' ' || family[end - 1] == '\\t' ||
          family[end - 1] == '\\n' || family[end - 1] == '\\r')) {
    --end;
  }
  family = family.substr(start, end - start);
  if (family.size() >= 2 &&
      ((family.front() == '"' && family.back() == '"') ||
       (family.front() == '\\'' && family.back() == '\\''))) {
    family = family.substr(1, family.size() - 2);
  }
  return family;
}

std::string BrowseForgeLowerASCII(std::string value) {
  for (char& c : value) {
    if (c >= 'A' && c <= 'Z') {
      c = static_cast<char>(c - 'A' + 'a');
    }
  }
  return value;
}

bool BrowseForgeIsGenericFontFamily(const std::string& family) {
  const std::string lowered = BrowseForgeLowerASCII(family);
  return lowered == "serif" || lowered == "sans-serif" ||
         lowered == "monospace" || lowered == "cursive" ||
         lowered == "fantasy" || lowered == "system-ui" ||
         lowered == "ui-serif" || lowered == "ui-sans-serif" ||
         lowered == "ui-monospace" || lowered == "ui-rounded" ||
         lowered == "emoji" || lowered == "math" || lowered == "fangsong";
}

bool BrowseForgeFontListContainsFamily(
    const std::unordered_set<std::string>& fonts,
    const std::string& candidate) {
  if (candidate.empty() || candidate.size() > 128) {
    return false;
  }
  for (char c : candidate) {
    if (c < 0x20 || c > 0x7e || c == '|') {
      return false;
    }
  }
  return fonts.find(candidate) != fonts.end();
}

bool BrowseForgeIsCSSIdentifierChar(char c) {
  return (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
         (c >= '0' && c <= '9') || c == '_' || c == '-';
}

size_t BrowseForgeSkipCSSFunction(const std::string& font_string,
                                  size_t start) {
  size_t name_end = start;
  while (name_end < font_string.size() &&
         BrowseForgeIsCSSIdentifierChar(font_string[name_end])) {
    ++name_end;
  }
  if (name_end == start || name_end >= font_string.size() ||
      font_string[name_end] != '(') {
    return std::string::npos;
  }
  size_t depth = 0;
  bool quoted = false;
  char quote = '\\0';
  for (size_t i = name_end; i < font_string.size(); ++i) {
    const char c = font_string[i];
    if (quoted) {
      if (c == quote) {
        quoted = false;
      }
      continue;
    }
    if (c == '"' || c == '\\'') {
      quoted = true;
      quote = c;
      continue;
    }
    if (c == '(') {
      ++depth;
      continue;
    }
    if (c == ')' && depth > 0 && --depth == 0) {
      return i + 1;
    }
  }
  return std::string::npos;
}

bool BrowseForgeTokenEquals(const std::string& font_string,
                            size_t start,
                            const char* token) {
  const size_t token_length = std::char_traits<char>::length(token);
  return font_string.compare(start, token_length, token) == 0 &&
         (start == 0 || !BrowseForgeIsCSSIdentifierChar(font_string[start - 1])) &&
         (start + token_length >= font_string.size() ||
          !BrowseForgeIsCSSIdentifierChar(font_string[start + token_length]));
}

size_t BrowseForgeSkipOptionalLineHeight(const std::string& font_string,
                                         size_t start) {
  size_t i = start;
  while (i < font_string.size() && font_string[i] == ' ') {
    ++i;
  }
  if (i >= font_string.size() || font_string[i] != '/') {
    return i;
  }
  ++i;
  while (i < font_string.size() && font_string[i] == ' ') {
    ++i;
  }
  while (i < font_string.size() && font_string[i] != ' ' &&
         font_string[i] != ',') {
    if ((font_string[i] >= 'A' && font_string[i] <= 'Z') ||
        (font_string[i] >= 'a' && font_string[i] <= 'z')) {
      const size_t function_end = BrowseForgeSkipCSSFunction(font_string, i);
      if (function_end != std::string::npos) {
        i = function_end;
        continue;
      }
    }
    ++i;
  }
  while (i < font_string.size() && font_string[i] == ' ') {
    ++i;
  }
  return i;
}

size_t BrowseForgeFindFontFamilyStart(const std::string& font_string) {
  const char* size_keywords[] = {"xx-small", "x-small", "small",  "medium",
                                 "large",    "x-large", "xx-large",
                                 "xxx-large", "larger",  "smaller"};
  const char* units[] = {"px",  "pt",  "pc",   "in",  "cm",  "mm",
                         "q",   "em",  "rem",  "ex",  "ch",  "lh",
                         "rlh", "vw",  "vh",   "vi",  "vb",  "vmin",
                         "vmax", "cap", "ic",   "%"};
  for (size_t i = 0; i < font_string.size(); ++i) {
    for (const char* keyword : size_keywords) {
      if (BrowseForgeTokenEquals(font_string, i, keyword)) {
        return BrowseForgeSkipOptionalLineHeight(
            font_string,
            i + std::char_traits<char>::length(keyword));
      }
    }
    if ((font_string[i] >= 'A' && font_string[i] <= 'Z') ||
        (font_string[i] >= 'a' && font_string[i] <= 'z')) {
      const size_t function_end = BrowseForgeSkipCSSFunction(font_string, i);
      if (function_end != std::string::npos) {
        return BrowseForgeSkipOptionalLineHeight(font_string, function_end);
      }
    }
    if ((font_string[i] < '0' || font_string[i] > '9') &&
        font_string[i] != '.') {
      continue;
    }
    size_t j = i + 1;
    while (j < font_string.size() &&
           ((font_string[j] >= '0' && font_string[j] <= '9') ||
            font_string[j] == '.')) {
      ++j;
    }
    for (const char* unit : units) {
      const size_t unit_length = std::char_traits<char>::length(unit);
      if (font_string.compare(j, unit_length, unit) != 0) {
        continue;
      }
      return BrowseForgeSkipOptionalLineHeight(font_string, j + unit_length);
    }
  }
  return std::string::npos;
}

BrowseForgeFontAllowlistDecision BrowseForgeFontFamilyAllowlistDecision(
    const String& font_string) {
  const std::unordered_set<std::string>& fonts =
      BrowseForgeFontAllowlistFamilies();
  if (fonts.empty()) {
    return BrowseForgeFontAllowlistDecision::kNoAllowlist;
  }
  const std::string css = font_string.Utf8();
  size_t start = BrowseForgeFindFontFamilyStart(css);
  if (start == std::string::npos || start >= css.size()) {
    return BrowseForgeFontAllowlistDecision::kDenied;
  }
  bool saw_non_generic_family = false;
  while (start < css.size()) {
    bool quoted = false;
    char quote = '\\0';
    size_t end = start;
    for (; end < css.size(); ++end) {
      const char c = css[end];
      if (quoted) {
        if (c == quote) {
          quoted = false;
        }
        continue;
      }
      if (c == '"' || c == '\\'') {
        quoted = true;
        quote = c;
        continue;
      }
      if (c == ',') {
        break;
      }
    }
    const std::string family = BrowseForgeTrimFontFamily(css.substr(start, end - start));
    if (!family.empty() && !BrowseForgeIsGenericFontFamily(family)) {
      saw_non_generic_family = true;
      if (!BrowseForgeFontListContainsFamily(fonts, family)) {
        return BrowseForgeFontAllowlistDecision::kDenied;
      }
    }
    if (end == css.size()) {
      break;
    }
    start = end + 1;
  }
  return saw_non_generic_family ? BrowseForgeFontAllowlistDecision::kAllowed
                                : BrowseForgeFontAllowlistDecision::kNoAllowlist;
}

}  // namespace

'''
LEGACY_ALLOCATING_FONTS_HELPER = '''namespace {

enum class BrowseForgeFontAllowlistDecision {
  kNoAllowlist,
  kAllowed,
  kDenied,
};

bool BrowseForgeFontListContainsFamily(const std::string& fonts,
                                       const std::string& candidate) {
  if (candidate.empty()) {
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
      if (printable && candidate == family) {
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

BrowseForgeFontAllowlistDecision BrowseForgeFontFamilyAllowlistDecision(
    const FontDescription& font_description) {
  const std::string fonts = base::CommandLine::ForCurrentProcess()
                                ->GetSwitchValueASCII("fingerprint-fonts-list");
  if (fonts.empty() || fonts.size() > 8192) {
    return BrowseForgeFontAllowlistDecision::kNoAllowlist;
  }
  bool saw_non_generic_family = false;
  for (const FontFamily* family = &font_description.Family(); family;
       family = family->Next()) {
    if (family->FamilyIsGeneric()) {
      continue;
    }
    saw_non_generic_family = true;
    if (!BrowseForgeFontListContainsFamily(fonts,
                                           family->FamilyName().Utf8())) {
      return BrowseForgeFontAllowlistDecision::kDenied;
    }
  }
  return saw_non_generic_family ? BrowseForgeFontAllowlistDecision::kAllowed
                                : BrowseForgeFontAllowlistDecision::kNoAllowlist;
}

}  // namespace

'''
LEGACY_SUBSTRING_FONTS_HELPER = '''namespace {

enum class BrowseForgeFontAllowlistDecision {
  kNoAllowlist,
  kAllowed,
  kDenied,
};

BrowseForgeFontAllowlistDecision BrowseForgeFontFamilyAllowlistDecision(
    const String& font_string) {
  const std::string fonts = base::CommandLine::ForCurrentProcess()
                                ->GetSwitchValueASCII("fingerprint-fonts-list");
  if (fonts.empty() || fonts.size() > 8192) {
    return BrowseForgeFontAllowlistDecision::kNoAllowlist;
  }
  const std::string query = font_string.Utf8();
  if (query.empty()) {
    return BrowseForgeFontAllowlistDecision::kDenied;
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
        return BrowseForgeFontAllowlistDecision::kAllowed;
      }
    }
    if (end == std::string::npos) {
      break;
    }
    start = end + 1;
  }
  return BrowseForgeFontAllowlistDecision::kDenied;
}

}  // namespace

'''
LEGACY_FONTS_HELPER = '''namespace {

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
  switch (BrowseForgeFontFamilyAllowlistDecision(font_string)) {
    case BrowseForgeFontAllowlistDecision::kAllowed:
      return true;
    case BrowseForgeFontAllowlistDecision::kDenied:
      return false;
    case BrowseForgeFontAllowlistDecision::kNoAllowlist:
      break;
  }

  FontSelector* font_selector = GetFontSelector();
'''
LEGACY_SUBSTRING_PATCHED_CHECK_PREFIX = '''  const Font* font = ResolveFontStyle(font_string);
  if (!font) {
    exception_state.ThrowDOMException(
        DOMExceptionCode::kSyntaxError,
        StrCat({"Could not resolve '", font_string, "' as a font."}));
    return false;
  }
  switch (BrowseForgeFontFamilyAllowlistDecision(font_string)) {
    case BrowseForgeFontAllowlistDecision::kAllowed:
      return true;
    case BrowseForgeFontAllowlistDecision::kDenied:
      return false;
    case BrowseForgeFontAllowlistDecision::kNoAllowlist:
      break;
  }

  FontSelector* font_selector = GetFontSelector();
'''
LEGACY_PATCHED_CHECK_PREFIX = '''  const Font* font = ResolveFontStyle(font_string);
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


CSS_FONT_SELECTOR_INCLUDE_ANCHOR = '#include "third_party/blink/renderer/core/css/css_font_selector.h"\n\n'
CSS_FONT_SELECTOR_INCLUDES = '#include <unordered_set>\n\n#include "base/command_line.h"\n'
CSS_FONT_SELECTOR_NAMESPACE_ANCHOR = 'namespace {\n\n'
CSS_FONT_SELECTOR_HELPER = '''bool BrowseForgeCSSFontFamilyBlocked(const AtomicString& family_name) {
  if (family_name.empty()) {
    return false;
  }
  if (family_name != AtomicString("Hiragino Sans W0")) {
    return false;
  }
  const std::string fonts = base::CommandLine::ForCurrentProcess()
                                ->GetSwitchValueASCII("fingerprint-fonts-list");
  if (fonts.empty()) {
    return false;
  }
  // BrowserLeaks' macOS dictionary includes this invalid synthetic Hiragino
  // weight family. Treat it as unavailable before platform font matching; the
  // real configured family remains "Hiragino Sans".
  return true;
}

'''
ORIGINAL_GET_FONT_DATA_PREFIX = '''const FontData* CSSFontSelector::GetFontData(
    const FontDescription& font_description,
    const FontFamily& font_family) {
  const auto& family_name = font_family.FamilyName();
  Document& document = GetTreeScope()->GetDocument();
'''
PATCHED_GET_FONT_DATA_PREFIX = ORIGINAL_GET_FONT_DATA_PREFIX
ORIGINAL_SEGMENTED_FONT_FACE_CHECK = '''  if (!font_family.FamilyIsGeneric()) {
'''
PATCHED_SEGMENTED_FONT_FACE_CHECK = '''  if (!font_family.FamilyIsGeneric() &&
      !BrowseForgeCSSFontFamilyBlocked(family_name)) {
'''
CSS_FONT_FAMILY_VALUE_ANCHOR = 'namespace blink {\n\n'
CSS_FONT_FAMILY_VALUE_HELPER = '''namespace {

const AtomicString& BrowseForgeSanitizeFontFamilyName(
    const AtomicString& family_name) {
  static const AtomicString* fallback = new AtomicString("sans-serif");
  if (family_name == AtomicString("Hiragino Sans W0")) {
    return *fallback;
  }
  return family_name;
}

}  // namespace

'''
ORIGINAL_FONT_FAMILY_VALUE_CACHE = '''  CSSValuePool::FontFamilyValueCache::AddResult entry =
      CssValuePool().GetFontFamilyCacheEntry(family_name);
  if (!entry.stored_value->value) {
    entry.stored_value->value =
        MakeGarbageCollected<CSSFontFamilyValue>(family_name);
  }
'''
PATCHED_FONT_FAMILY_VALUE_CACHE = '''  const AtomicString& sanitized_family_name =
      BrowseForgeSanitizeFontFamilyName(family_name);
  CSSValuePool::FontFamilyValueCache::AddResult entry =
      CssValuePool().GetFontFamilyCacheEntry(sanitized_family_name);
  if (!entry.stored_value->value) {
    entry.stored_value->value =
        MakeGarbageCollected<CSSFontFamilyValue>(sanitized_family_name);
  }
'''


def validate_chromium_src(src: Path) -> None:
    if not (src / ".git").exists():
        raise SystemExit(f"Chromium source checkout is not ready: {src}")
    if not (src / FONT_FACE_SET_CC).is_file():
        raise SystemExit(f"Chromium FontFaceSet source file is missing: {src / FONT_FACE_SET_CC}")
    if not (src / CSS_FONT_SELECTOR_CC).is_file():
        raise SystemExit(f"Chromium CSSFontSelector source file is missing: {src / CSS_FONT_SELECTOR_CC}")
    if not (src / CSS_FONT_FAMILY_VALUE_CC).is_file():
        raise SystemExit(f"Chromium CSSFontFamilyValue source file is missing: {src / CSS_FONT_FAMILY_VALUE_CC}")


def ensure_include(text: str) -> str:
    patched = text
    if UNORDERED_SET_INCLUDE not in patched:
        patched = UNORDERED_SET_INCLUDE + patched
    if COMMAND_LINE_INCLUDE not in patched:
        if INCLUDE_ANCHOR not in patched:
            raise SystemExit("font_face_set.cc include anchor not found")
        patched = patched.replace(INCLUDE_ANCHOR, INCLUDE_ANCHOR + COMMAND_LINE_INCLUDE, 1)
    return patched


def patch_font_face_set(text: str) -> str:
    patched = ensure_include(text)
    if FONTS_HELPER not in patched:
        if LEGACY_ALLOCATING_FONTS_HELPER in patched:
            patched = patched.replace(LEGACY_ALLOCATING_FONTS_HELPER, FONTS_HELPER, 1)
        elif LEGACY_SUBSTRING_FONTS_HELPER in patched:
            patched = patched.replace(LEGACY_SUBSTRING_FONTS_HELPER, FONTS_HELPER, 1)
        elif LEGACY_FONTS_HELPER in patched:
            patched = patched.replace(LEGACY_FONTS_HELPER, FONTS_HELPER, 1)
        else:
            if NAMESPACE_ANCHOR not in patched:
                raise SystemExit("font_face_set.cc namespace anchor not found")
            patched = patched.replace(NAMESPACE_ANCHOR, NAMESPACE_ANCHOR + FONTS_HELPER, 1)
    if PATCHED_CHECK_PREFIX in patched:
        return patched
    if LEGACY_SUBSTRING_PATCHED_CHECK_PREFIX in patched:
        return patched.replace(LEGACY_SUBSTRING_PATCHED_CHECK_PREFIX, PATCHED_CHECK_PREFIX, 1)
    if LEGACY_PATCHED_CHECK_PREFIX in patched:
        return patched.replace(LEGACY_PATCHED_CHECK_PREFIX, PATCHED_CHECK_PREFIX, 1)
    if ORIGINAL_CHECK_PREFIX not in patched:
        raise SystemExit("FontFaceSet::check implementation anchor not found")
    return patched.replace(ORIGINAL_CHECK_PREFIX, PATCHED_CHECK_PREFIX, 1)


def patch_css_font_selector(text: str) -> str:
    patched = text
    if CSS_FONT_SELECTOR_INCLUDES not in patched:
        if CSS_FONT_SELECTOR_INCLUDE_ANCHOR not in patched:
            raise SystemExit("css_font_selector.cc include anchor not found")
        patched = patched.replace(
            CSS_FONT_SELECTOR_INCLUDE_ANCHOR,
            CSS_FONT_SELECTOR_INCLUDE_ANCHOR + CSS_FONT_SELECTOR_INCLUDES,
            1,
        )
    if CSS_FONT_SELECTOR_HELPER not in patched:
        if CSS_FONT_SELECTOR_NAMESPACE_ANCHOR not in patched:
            raise SystemExit("css_font_selector.cc namespace anchor not found")
        patched = patched.replace(
            CSS_FONT_SELECTOR_NAMESPACE_ANCHOR,
            CSS_FONT_SELECTOR_NAMESPACE_ANCHOR + CSS_FONT_SELECTOR_HELPER,
            1,
        )
    if ORIGINAL_GET_FONT_DATA_PREFIX not in patched:
        raise SystemExit("CSSFontSelector::GetFontData implementation anchor not found")
    if PATCHED_SEGMENTED_FONT_FACE_CHECK in patched:
        return patched
    if ORIGINAL_SEGMENTED_FONT_FACE_CHECK not in patched:
        raise SystemExit("CSSFontSelector segmented font face anchor not found")
    return patched.replace(ORIGINAL_SEGMENTED_FONT_FACE_CHECK, PATCHED_SEGMENTED_FONT_FACE_CHECK, 1)

def patch_css_font_family_value(text: str) -> str:
    patched = text
    if CSS_FONT_FAMILY_VALUE_HELPER not in patched:
        if CSS_FONT_FAMILY_VALUE_ANCHOR not in patched:
            raise SystemExit("css_font_family_value.cc namespace anchor not found")
        patched = patched.replace(
            CSS_FONT_FAMILY_VALUE_ANCHOR,
            CSS_FONT_FAMILY_VALUE_ANCHOR + CSS_FONT_FAMILY_VALUE_HELPER,
            1,
        )
    if PATCHED_FONT_FAMILY_VALUE_CACHE in patched:
        return patched
    if ORIGINAL_FONT_FAMILY_VALUE_CACHE not in patched:
        raise SystemExit("CSSFontFamilyValue::Create cache anchor not found")
    return patched.replace(ORIGINAL_FONT_FAMILY_VALUE_CACHE, PATCHED_FONT_FAMILY_VALUE_CACHE, 1)



def write_if_changed(path: Path, content: str) -> bool:
    original = path.read_text(encoding="utf-8")
    if content == original:
        return False
    path.write_text(content, encoding="utf-8")
    return True


def apply_patch(src: Path) -> list[Path]:
    validate_chromium_src(src)
    font_face_path = src / FONT_FACE_SET_CC
    css_selector_path = src / CSS_FONT_SELECTOR_CC
    css_family_value_path = src / CSS_FONT_FAMILY_VALUE_CC
    write_if_changed(font_face_path, patch_font_face_set(font_face_path.read_text(encoding="utf-8")))
    write_if_changed(css_selector_path, patch_css_font_selector(css_selector_path.read_text(encoding="utf-8")))
    write_if_changed(css_family_value_path, patch_css_font_family_value(css_family_value_path.read_text(encoding="utf-8")))
    return [FONT_FACE_SET_CC, CSS_FONT_SELECTOR_CC, CSS_FONT_FAMILY_VALUE_CC]


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply BrowseForge FontFaceSet font availability source patch")
    parser.add_argument("--chromium-src", type=Path, default=DEFAULT_CHROMIUM_SRC)
    parser.add_argument("--check", action="store_true", help="validate checkout and patch anchors without writing")
    args = parser.parse_args()

    src = args.chromium_src.resolve()
    validate_chromium_src(src)
    if args.check:
        patch_font_face_set((src / FONT_FACE_SET_CC).read_text(encoding="utf-8"))
        patch_css_font_selector((src / CSS_FONT_SELECTOR_CC).read_text(encoding="utf-8"))
        print(f"ready: {src / FONT_FACE_SET_CC}")
        print(f"ready: {src / CSS_FONT_SELECTOR_CC}")
        return
    for path in apply_patch(src):
        print(path.as_posix())


if __name__ == "__main__":
    main()
