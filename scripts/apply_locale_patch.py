#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_CHROMIUM_SRC = Path("/Users/chun/Projects/browser-source/browseforge-chromium/src")
NAVIGATOR_LANGUAGE_CC = Path("third_party/blink/renderer/core/frame/navigator_language.cc")

NAMESPACE_ANCHOR = 'namespace blink {\n\n'

LOCALE_HELPER = '''namespace {\n\nString BrowseForgeAcceptLanguagesOverride() {\n  const base::CommandLine* command_line =\n      base::CommandLine::ForCurrentProcess();\n  std::string accept_languages =\n      command_line->GetSwitchValueASCII("fingerprint-accept-language");\n  if (accept_languages.empty()) {\n    accept_languages = command_line->GetSwitchValueASCII("fingerprint-locale");\n  }\n  if (accept_languages.empty() || accept_languages.size() > 256) {\n    return String();\n  }\n  for (char c : accept_languages) {\n    const bool valid = (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||\n                       (c >= '0' && c <= '9') || c == '_' || c == '-' ||\n                       c == ',' || c == ';' || c == '=' || c == '.' ||\n                       c == ' ';\n    if (!valid) {\n      return String();\n    }\n  }\n  return String::FromUtf8(accept_languages);\n}\n\n}  // namespace\n\n'''

ORIGINAL_DIRTY = '''bool NavigatorLanguage::IsLanguagesDirty() const {\n  // Check if the language has override. If so, consider the language is dirty.\n  // This is required, as `IsLanguagesDirty` properly is used to cache\n  // v8 value of `languages` in `navigator_language.idl`, while the\n  // `languages_dirty_` represents the state of the `languages_`. If `languages`\n  // was accessed, the `languages_dirty_` is set to false, but the\n  // `navigator_language.idl` still holds the old cached value.\n  String accept_languages_override;\n  probe::ApplyAcceptLanguageOverride(execution_context_,\n                                     &accept_languages_override);\n\n  return languages_dirty_ || !accept_languages_override.IsNull();\n}\n'''
PATCHED_DIRTY = '''bool NavigatorLanguage::IsLanguagesDirty() const {\n  // Check if the language has override. If so, consider the language is dirty.\n  // This is required, as `IsLanguagesDirty` properly is used to cache\n  // v8 value of `languages` in `navigator_language.idl`, while the\n  // `languages_dirty_` represents the state of the `languages_`. If `languages`\n  // was accessed, the `languages_dirty_` is set to false, but the\n  // `navigator_language.idl` still holds the old cached value.\n  if (!BrowseForgeAcceptLanguagesOverride().empty()) {\n    return true;\n  }\n\n  String accept_languages_override;\n  probe::ApplyAcceptLanguageOverride(execution_context_,\n                                     &accept_languages_override);\n\n  return languages_dirty_ || !accept_languages_override.IsNull();\n}\n'''

ORIGINAL_ENSURE = '''void NavigatorLanguage::EnsureUpdatedLanguage() {\n  String accept_languages_override;\n  probe::ApplyAcceptLanguageOverride(execution_context_,\n                                     &accept_languages_override);\n  if (!accept_languages_override.IsNull()) {\n    // If the language has override, force use the override regardless of the\n    // `languages_dirty_` state. This is required to allow for workers to\n    // respect the override.\n    languages_ = ParseAndSanitize(accept_languages_override);\n    // Mark the language as dirty, so that if the override is removed, the\n    // language will be updated.\n    languages_dirty_ = true;\n    return;\n  }\n\n  if (languages_dirty_) {\n'''
PATCHED_ENSURE = '''void NavigatorLanguage::EnsureUpdatedLanguage() {\n  String browseforge_accept_languages = BrowseForgeAcceptLanguagesOverride();\n  if (!browseforge_accept_languages.empty()) {\n    languages_ = ParseAndSanitize(browseforge_accept_languages);\n    languages_dirty_ = true;\n    return;\n  }\n\n  String accept_languages_override;\n  probe::ApplyAcceptLanguageOverride(execution_context_,\n                                     &accept_languages_override);\n  if (!accept_languages_override.IsNull()) {\n    // If the language has override, force use the override regardless of the\n    // `languages_dirty_` state. This is required to allow for workers to\n    // respect the override.\n    languages_ = ParseAndSanitize(accept_languages_override);\n    // Mark the language as dirty, so that if the override is removed, the\n    // language will be updated.\n    languages_dirty_ = true;\n    return;\n  }\n\n  if (languages_dirty_) {\n'''


def validate_chromium_src(src: Path) -> None:
    if not (src / ".git").exists():
        raise SystemExit(f"Chromium source checkout is not ready: {src}")
    if not (src / NAVIGATOR_LANGUAGE_CC).is_file():
        raise SystemExit(f"Chromium navigator language source file is missing: {src / NAVIGATOR_LANGUAGE_CC}")


def patch_locale(text: str) -> str:
    patched = text
    if "BrowseForgeAcceptLanguagesOverride" not in patched:
        if NAMESPACE_ANCHOR not in patched:
            raise SystemExit("navigator_language.cc namespace anchor not found")
        patched = patched.replace(NAMESPACE_ANCHOR, NAMESPACE_ANCHOR + LOCALE_HELPER, 1)
    replacements = [
        (ORIGINAL_DIRTY, PATCHED_DIRTY, "NavigatorLanguage::IsLanguagesDirty"),
        (ORIGINAL_ENSURE, PATCHED_ENSURE, "NavigatorLanguage::EnsureUpdatedLanguage"),
    ]
    for original, replacement, label in replacements:
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
    path = src / NAVIGATOR_LANGUAGE_CC
    write_if_changed(path, patch_locale(path.read_text(encoding="utf-8")))
    return [NAVIGATOR_LANGUAGE_CC]


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply BrowseForge navigator language source patch")
    parser.add_argument("--chromium-src", type=Path, default=DEFAULT_CHROMIUM_SRC)
    parser.add_argument("--check", action="store_true", help="validate checkout and patch anchors without writing")
    args = parser.parse_args()

    src = args.chromium_src.resolve()
    validate_chromium_src(src)
    if args.check:
        patch_locale((src / NAVIGATOR_LANGUAGE_CC).read_text(encoding="utf-8"))
        print(f"ready: {src / NAVIGATOR_LANGUAGE_CC}")
        return
    for path in apply_patch(src):
        print(path.as_posix())


if __name__ == "__main__":
    main()
