#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_CHROMIUM_SRC = Path("/Users/chun/Projects/browser-source/browseforge-chromium/src")
PROFILE_NETWORK_CONTEXT_SERVICE_CC = Path("chrome/browser/net/profile_network_context_service.cc")

NAMESPACE_ANCHOR = "namespace {\n"

ACCEPT_LANGUAGE_HEADER_HELPER = '''namespace {

std::string BrowseForgeAcceptLanguagesHeaderOverride() {
  const base::CommandLine* command_line =
      base::CommandLine::ForCurrentProcess();
  std::string accept_languages =
      command_line->GetSwitchValueASCII("fingerprint-accept-language");
  if (accept_languages.empty() || accept_languages.size() > 256) {
    return std::string();
  }
  for (char c : accept_languages) {
    const bool valid = (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z') ||
                       (c >= '0' && c <= '9') || c == '_' || c == '-' ||
                       c == ',' || c == ';' || c == '=' || c == '.' ||
                       c == ' ';
    if (!valid) {
      return std::string();
    }
  }
  return accept_languages;
}

'''

ORIGINAL_COMPUTE = '''std::string ComputeAcceptLanguageFromPref(const std::string& language_pref) {
  std::string accept_languages_str =
      net::HttpUtil::ExpandLanguageList(language_pref);
  return net::HttpUtil::GenerateAcceptLanguageHeader(accept_languages_str);
}
'''

PATCHED_COMPUTE = '''std::string ComputeAcceptLanguageFromPref(const std::string& language_pref) {
  std::string browseforge_accept_languages =
      BrowseForgeAcceptLanguagesHeaderOverride();
  if (!browseforge_accept_languages.empty()) {
    std::string browseforge_accept_languages_str =
        net::HttpUtil::ExpandLanguageList(browseforge_accept_languages);
    return net::HttpUtil::GenerateAcceptLanguageHeader(
        browseforge_accept_languages_str);
  }

  std::string accept_languages_str =
      net::HttpUtil::ExpandLanguageList(language_pref);
  return net::HttpUtil::GenerateAcceptLanguageHeader(accept_languages_str);
}
'''


def validate_chromium_src(src: Path) -> None:
    if not (src / ".git").exists():
        raise SystemExit(f"Chromium source checkout is not ready: {src}")
    if not (src / PROFILE_NETWORK_CONTEXT_SERVICE_CC).is_file():
        raise SystemExit(
            "Chromium profile network context source file is missing: "
            f"{src / PROFILE_NETWORK_CONTEXT_SERVICE_CC}"
        )


def patch_accept_language_header(text: str) -> str:
    patched = text
    if "BrowseForgeAcceptLanguagesHeaderOverride" not in patched:
        if NAMESPACE_ANCHOR not in patched:
            raise SystemExit("profile_network_context_service.cc namespace anchor not found")
        patched = patched.replace(NAMESPACE_ANCHOR, ACCEPT_LANGUAGE_HEADER_HELPER, 1)
    if PATCHED_COMPUTE not in patched:
        if ORIGINAL_COMPUTE not in patched:
            raise SystemExit("ComputeAcceptLanguageFromPref anchor not found")
        patched = patched.replace(ORIGINAL_COMPUTE, PATCHED_COMPUTE, 1)
    return patched


def write_if_changed(path: Path, content: str) -> bool:
    original = path.read_text(encoding="utf-8")
    if content == original:
        return False
    path.write_text(content, encoding="utf-8")
    return True


def apply_patch(src: Path) -> list[Path]:
    validate_chromium_src(src)
    path = src / PROFILE_NETWORK_CONTEXT_SERVICE_CC
    write_if_changed(path, patch_accept_language_header(path.read_text(encoding="utf-8")))
    return [PROFILE_NETWORK_CONTEXT_SERVICE_CC]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Apply BrowseForge HTTP Accept-Language header source patch"
    )
    parser.add_argument("--chromium-src", type=Path, default=DEFAULT_CHROMIUM_SRC)
    parser.add_argument("--check", action="store_true", help="validate checkout and patch anchors without writing")
    args = parser.parse_args()

    src = args.chromium_src.resolve()
    validate_chromium_src(src)
    if args.check:
        patch_accept_language_header((src / PROFILE_NETWORK_CONTEXT_SERVICE_CC).read_text(encoding="utf-8"))
        print(f"ready: {src / PROFILE_NETWORK_CONTEXT_SERVICE_CC}")
        return
    for path in apply_patch(src):
        print(path.as_posix())


if __name__ == "__main__":
    main()
