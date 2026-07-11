from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "apply_accept_language_header_patch.py"

spec = importlib.util.spec_from_file_location("apply_accept_language_header_patch", SCRIPT)
apply_accept_language_header_patch = importlib.util.module_from_spec(spec)
sys.modules["apply_accept_language_header_patch"] = apply_accept_language_header_patch
assert spec.loader is not None
spec.loader.exec_module(apply_accept_language_header_patch)

PROFILE_NETWORK_CONTEXT_SERVICE_FIXTURE = '''#include "base/command_line.h"
#include "net/http/http_util.h"

namespace {

std::string ComputeAcceptLanguageFromPref(const std::string& language_pref) {
  std::string accept_languages_str =
      net::HttpUtil::ExpandLanguageList(language_pref);
  return net::HttpUtil::GenerateAcceptLanguageHeader(accept_languages_str);
}

}  // namespace
'''

CHROME_CONTENT_BROWSER_CLIENT_FIXTURE = '''std::string ChromeContentBrowserClient::GetAcceptLangs(
    content::BrowserContext* context) {
  Profile* profile = Profile::FromBrowserContext(context);
  return profile->GetPrefs()->GetString(language::prefs::kAcceptLanguages);
}
'''

REDUCE_ACCEPT_LANGUAGE_SERVICE_FIXTURE = '''#include <string>

void ReduceAcceptLanguageService::UpdateAcceptLanguage() {
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


class ApplyAcceptLanguageHeaderPatchTests(unittest.TestCase):
    def test_patches_accept_language_header_override(self) -> None:
        patched = apply_accept_language_header_patch.patch_accept_language_header(
            PROFILE_NETWORK_CONTEXT_SERVICE_FIXTURE
        )

        self.assertIn("BrowseForgeAcceptLanguagesHeaderOverride()", patched)
        self.assertIn('GetSwitchValueASCII("fingerprint-accept-language")', patched)
        self.assertRegex(patched, r"\.size\(\)\s*>\s*\d+")
        self.assertIn("for (char c :", patched)
        self.assertIn("c >= 'A' && c <= 'Z'", patched)
        self.assertIn("c >= 'a' && c <= 'z'", patched)
        self.assertIn("c >= '0' && c <= '9'", patched)
        self.assertIn("c == '-'", patched)
        self.assertIn("c == ','", patched)

        function_start = patched.index("std::string ComputeAcceptLanguageFromPref")
        function_end = patched.index("\n}\n", function_start)
        function_body = patched[function_start:function_end]
        self.assertIn("BrowseForgeAcceptLanguagesHeaderOverride()", function_body)
        self.assertLess(
            function_body.index("BrowseForge"),
            function_body.index("net::HttpUtil::ExpandLanguageList(language_pref)"),
        )
        self.assertIn("net::HttpUtil::GenerateAcceptLanguageHeader", function_body)

    def test_patch_is_idempotent(self) -> None:
        patched_once = apply_accept_language_header_patch.patch_accept_language_header(
            PROFILE_NETWORK_CONTEXT_SERVICE_FIXTURE
        )
        patched_twice = apply_accept_language_header_patch.patch_accept_language_header(
            patched_once
        )

        self.assertEqual(patched_once, patched_twice)
        self.assertEqual(1, patched_once.count("std::string BrowseForgeAcceptLanguagesHeaderOverride()"))
        self.assertEqual(
            1,
            patched_once.count('GetSwitchValueASCII("fingerprint-accept-language")'),
        )

    def test_patches_content_accept_language_source(self) -> None:
        patched = apply_accept_language_header_patch.patch_content_accept_languages(
            CHROME_CONTENT_BROWSER_CLIENT_FIXTURE
        )

        self.assertIn("ChromeContentBrowserClient::GetAcceptLangs", patched)
        self.assertIn("base::CommandLine::ForCurrentProcess()", patched)
        self.assertIn('GetSwitchValueASCII("fingerprint-accept-language")', patched)
        self.assertLess(
            patched.index("fingerprint-accept-language"),
            patched.index("Profile::FromBrowserContext"),
        )
        self.assertEqual(
            patched,
            apply_accept_language_header_patch.patch_content_accept_languages(patched),
        )

    def test_patches_reduce_accept_language_service(self) -> None:
        patched = apply_accept_language_header_patch.patch_reduce_accept_language_service(
            REDUCE_ACCEPT_LANGUAGE_SERVICE_FIXTURE
        )

        self.assertIn('#include "base/command_line.h"', patched)
        self.assertIn("ReduceAcceptLanguageService::UpdateAcceptLanguage", patched)
        self.assertIn("base::CommandLine::ForCurrentProcess()", patched)
        self.assertIn('GetSwitchValueASCII("fingerprint-accept-language")', patched)
        self.assertLess(
            patched.index("fingerprint-accept-language"),
            patched.index("pref_accept_language_.GetValue()"),
        )
        self.assertEqual(
            patched,
            apply_accept_language_header_patch.patch_reduce_accept_language_service(patched),
        )

    def test_apply_patch_updates_external_checkout_shape(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "src"
            (src / ".git").mkdir(parents=True)
            profile_network_path = (
                src / apply_accept_language_header_patch.PROFILE_NETWORK_CONTEXT_SERVICE_CC
            )
            profile_network_path.parent.mkdir(parents=True)
            profile_network_path.write_text(
                PROFILE_NETWORK_CONTEXT_SERVICE_FIXTURE,
                encoding="utf-8",
            )

            content_browser_client_path = (
                src / apply_accept_language_header_patch.CHROME_CONTENT_BROWSER_CLIENT_CC
            )
            content_browser_client_path.parent.mkdir(parents=True, exist_ok=True)
            content_browser_client_path.write_text(
                CHROME_CONTENT_BROWSER_CLIENT_FIXTURE,
                encoding="utf-8",
            )

            reduce_accept_language_service_path = (
                src / apply_accept_language_header_patch.REDUCE_ACCEPT_LANGUAGE_SERVICE_CC
            )
            reduce_accept_language_service_path.parent.mkdir(parents=True, exist_ok=True)
            reduce_accept_language_service_path.write_text(
                REDUCE_ACCEPT_LANGUAGE_SERVICE_FIXTURE,
                encoding="utf-8",
            )

            changed = apply_accept_language_header_patch.apply_patch(src)

            self.assertEqual(
                [
                    apply_accept_language_header_patch.PROFILE_NETWORK_CONTEXT_SERVICE_CC,
                    apply_accept_language_header_patch.CHROME_CONTENT_BROWSER_CLIENT_CC,
                    apply_accept_language_header_patch.REDUCE_ACCEPT_LANGUAGE_SERVICE_CC,
                ],
                changed,
            )
            self.assertEqual(
                Path("chrome/browser/net/profile_network_context_service.cc"),
                apply_accept_language_header_patch.PROFILE_NETWORK_CONTEXT_SERVICE_CC,
            )
            self.assertIn(
                "fingerprint-accept-language",
                profile_network_path.read_text(encoding="utf-8"),
            )
            self.assertEqual(
                Path("chrome/browser/chrome_content_browser_client.cc"),
                apply_accept_language_header_patch.CHROME_CONTENT_BROWSER_CLIENT_CC,
            )
            self.assertIn(
                "fingerprint-accept-language",
                content_browser_client_path.read_text(encoding="utf-8"),
            )
            self.assertEqual(
                Path("components/reduce_accept_language/browser/reduce_accept_language_service.cc"),
                apply_accept_language_header_patch.REDUCE_ACCEPT_LANGUAGE_SERVICE_CC,
            )
            self.assertIn(
                "fingerprint-accept-language",
                reduce_accept_language_service_path.read_text(encoding="utf-8"),
            )


if __name__ == "__main__":
    unittest.main()
