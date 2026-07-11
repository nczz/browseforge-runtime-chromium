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

            changed = apply_accept_language_header_patch.apply_patch(src)

            self.assertEqual(
                [apply_accept_language_header_patch.PROFILE_NETWORK_CONTEXT_SERVICE_CC],
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


if __name__ == "__main__":
    unittest.main()
