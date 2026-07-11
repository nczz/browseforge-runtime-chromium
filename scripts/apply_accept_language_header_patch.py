#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_CHROMIUM_SRC = Path("/Users/chun/Projects/browser-source/browseforge-chromium/src")
PROFILE_NETWORK_CONTEXT_SERVICE_CC = Path("chrome/browser/net/profile_network_context_service.cc")
CHROME_CONTENT_BROWSER_CLIENT_CC = Path("chrome/browser/chrome_content_browser_client.cc")
REDUCE_ACCEPT_LANGUAGE_SERVICE_CC = Path("components/reduce_accept_language/browser/reduce_accept_language_service.cc")

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

ORIGINAL_CONTENT_GET_ACCEPT_LANGS = '''std::string ChromeContentBrowserClient::GetAcceptLangs(
    content::BrowserContext* context) {
  Profile* profile = Profile::FromBrowserContext(context);
  return profile->GetPrefs()->GetString(language::prefs::kAcceptLanguages);
}
'''

PATCHED_CONTENT_GET_ACCEPT_LANGS = '''std::string ChromeContentBrowserClient::GetAcceptLangs(
    content::BrowserContext* context) {
  const base::CommandLine* command_line =
      base::CommandLine::ForCurrentProcess();
  std::string browseforge_accept_languages =
      command_line->GetSwitchValueASCII("fingerprint-accept-language");
  if (!browseforge_accept_languages.empty() &&
      browseforge_accept_languages.size() <= 256) {
    return browseforge_accept_languages;
  }

  Profile* profile = Profile::FromBrowserContext(context);
  return profile->GetPrefs()->GetString(language::prefs::kAcceptLanguages);
}
'''

REDUCE_SERVICE_INCLUDE_ANCHOR = '#include <string>\n'
REDUCE_SERVICE_COMMAND_LINE_INCLUDE = '#include <string>\n\n#include "base/command_line.h"\n'

ORIGINAL_REDUCE_UPDATE_ACCEPT_LANGUAGE = '''void ReduceAcceptLanguageService::UpdateAcceptLanguage() {
  // In incognito mode return a genericized language list.
  std::string accept_languages_str = net::HttpUtil::ExpandLanguageList(
      is_incognito_
          ? language::GetIncognitoLanguageList(pref_accept_language_.GetValue())
          : pref_accept_language_.GetValue());
  user_accept_languages_ = base::SplitString(
      accept_languages_str, ",", base::TRIM_WHITESPACE, base::SPLIT_WANT_ALL);

  base::UmaHistogramBoolean(
      "ReduceAcceptLanguage.AcceptLanguagePrefValueIsEmpty",
      user_accept_languages_.empty());
}
'''

PATCHED_REDUCE_UPDATE_ACCEPT_LANGUAGE = '''void ReduceAcceptLanguageService::UpdateAcceptLanguage() {
  const base::CommandLine* command_line =
      base::CommandLine::ForCurrentProcess();
  std::string browseforge_accept_languages =
      command_line->GetSwitchValueASCII("fingerprint-accept-language");
  if (browseforge_accept_languages.empty() ||
      browseforge_accept_languages.size() > 256) {
    // In incognito mode return a genericized language list.
    browseforge_accept_languages =
        is_incognito_
            ? language::GetIncognitoLanguageList(
                  pref_accept_language_.GetValue())
            : pref_accept_language_.GetValue();
  }

  std::string accept_languages_str =
      net::HttpUtil::ExpandLanguageList(browseforge_accept_languages);
  user_accept_languages_ = base::SplitString(
      accept_languages_str, ",", base::TRIM_WHITESPACE, base::SPLIT_WANT_ALL);

  base::UmaHistogramBoolean(
      "ReduceAcceptLanguage.AcceptLanguagePrefValueIsEmpty",
      user_accept_languages_.empty());
}
'''


def validate_chromium_src(src: Path) -> None:
    if not (src / ".git").exists():
        raise SystemExit(f"Chromium source checkout is not ready: {src}")
    required_files = [
        PROFILE_NETWORK_CONTEXT_SERVICE_CC,
        CHROME_CONTENT_BROWSER_CLIENT_CC,
        REDUCE_ACCEPT_LANGUAGE_SERVICE_CC,
    ]
    for required_file in required_files:
        if not (src / required_file).is_file():
            raise SystemExit(
                "Chromium source file is missing: "
                f"{src / required_file}"
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


def patch_content_accept_languages(text: str) -> str:
    if PATCHED_CONTENT_GET_ACCEPT_LANGS in text:
        return text
    if ORIGINAL_CONTENT_GET_ACCEPT_LANGS not in text:
        raise SystemExit("ChromeContentBrowserClient::GetAcceptLangs anchor not found")
    return text.replace(
        ORIGINAL_CONTENT_GET_ACCEPT_LANGS,
        PATCHED_CONTENT_GET_ACCEPT_LANGS,
        1,
    )


def patch_reduce_accept_language_service(text: str) -> str:
    patched = text
    if '#include "base/command_line.h"' not in patched:
        if REDUCE_SERVICE_INCLUDE_ANCHOR not in patched:
            raise SystemExit("reduce_accept_language_service.cc include anchor not found")
        patched = patched.replace(
            REDUCE_SERVICE_INCLUDE_ANCHOR,
            REDUCE_SERVICE_COMMAND_LINE_INCLUDE,
            1,
        )
    if PATCHED_REDUCE_UPDATE_ACCEPT_LANGUAGE not in patched:
        if ORIGINAL_REDUCE_UPDATE_ACCEPT_LANGUAGE not in patched:
            raise SystemExit("ReduceAcceptLanguageService::UpdateAcceptLanguage anchor not found")
        patched = patched.replace(
            ORIGINAL_REDUCE_UPDATE_ACCEPT_LANGUAGE,
            PATCHED_REDUCE_UPDATE_ACCEPT_LANGUAGE,
            1,
        )
    return patched


def write_if_changed(path: Path, content: str) -> bool:
    original = path.read_text(encoding="utf-8")
    if content == original:
        return False
    path.write_text(content, encoding="utf-8")
    return True


def apply_patch(src: Path) -> list[Path]:
    validate_chromium_src(src)
    profile_network_path = src / PROFILE_NETWORK_CONTEXT_SERVICE_CC
    content_browser_client_path = src / CHROME_CONTENT_BROWSER_CLIENT_CC
    reduce_accept_language_service_path = src / REDUCE_ACCEPT_LANGUAGE_SERVICE_CC
    write_if_changed(
        profile_network_path,
        patch_accept_language_header(profile_network_path.read_text(encoding="utf-8")),
    )
    write_if_changed(
        content_browser_client_path,
        patch_content_accept_languages(
            content_browser_client_path.read_text(encoding="utf-8")
        ),
    )
    write_if_changed(
        reduce_accept_language_service_path,
        patch_reduce_accept_language_service(
            reduce_accept_language_service_path.read_text(encoding="utf-8")
        ),
    )
    return [
        PROFILE_NETWORK_CONTEXT_SERVICE_CC,
        CHROME_CONTENT_BROWSER_CLIENT_CC,
        REDUCE_ACCEPT_LANGUAGE_SERVICE_CC,
    ]


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
        patch_content_accept_languages((src / CHROME_CONTENT_BROWSER_CLIENT_CC).read_text(encoding="utf-8"))
        patch_reduce_accept_language_service((src / REDUCE_ACCEPT_LANGUAGE_SERVICE_CC).read_text(encoding="utf-8"))
        print(f"ready: {src / PROFILE_NETWORK_CONTEXT_SERVICE_CC}")
        print(f"ready: {src / CHROME_CONTENT_BROWSER_CLIENT_CC}")
        print(f"ready: {src / REDUCE_ACCEPT_LANGUAGE_SERVICE_CC}")
        return
    for path in apply_patch(src):
        print(path.as_posix())


if __name__ == "__main__":
    main()
