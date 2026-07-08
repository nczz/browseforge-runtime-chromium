from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "apply_webrtc_patch.py"

spec = importlib.util.spec_from_file_location("apply_webrtc_patch", SCRIPT)
assert spec and spec.loader
apply_webrtc_patch = importlib.util.module_from_spec(spec)
sys.modules["apply_webrtc_patch"] = apply_webrtc_patch
spec.loader.exec_module(apply_webrtc_patch)

ICE_FIXTURE = '''#include "third_party/blink/renderer/modules/peerconnection/rtc_ice_candidate.h"

#include <utility>

#include "third_party/blink/renderer/bindings/core/v8/script_value.h"

namespace blink {

String RTCIceCandidate::candidate() const {
  return platform_candidate_->Candidate();
}

String RTCIceCandidate::address() const {
  return platform_candidate_->Address();
}

String RTCIceCandidate::relatedAddress() const {
  return platform_candidate_->RelatedAddress();
}

ScriptObject RTCIceCandidate::toJSONForBinding(ScriptState* script_state) {
  V8ObjectBuilder result(script_state);
  result.AddString("candidate", platform_candidate_->Candidate());
  return result.ToScriptObject();
}

}  // namespace blink
'''


class ApplyWebRTCPatchTests(unittest.TestCase):
    def test_patches_candidate_address_and_json(self) -> None:
        patched = apply_webrtc_patch.patch_webrtc(ICE_FIXTURE)
        self.assertIn('#include "base/command_line.h"', patched)
        self.assertIn('GetSwitchValueASCII(\n      "fingerprint-webrtc-ip")', patched)
        self.assertIn('BrowseForgeWebRTCCandidateOverride(platform_candidate_->Candidate()', patched)
        self.assertIn("String rewritten = candidate;", patched)
        self.assertIn('return ip.empty() ? platform_candidate_->Address() : ip;', patched)
        self.assertIn('result.AddString("candidate", candidate());', patched)
        self.assertIn('ip == "auto"', patched)

    def test_patch_is_idempotent(self) -> None:
        patched_once = apply_webrtc_patch.patch_webrtc(ICE_FIXTURE)
        patched_twice = apply_webrtc_patch.patch_webrtc(patched_once)
        self.assertEqual(patched_once, patched_twice)

    def test_apply_patch_updates_external_checkout_shape(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "src"
            ice_path = src / apply_webrtc_patch.RTC_ICE_CANDIDATE_CC
            ice_path.parent.mkdir(parents=True)
            (src / ".git").mkdir()
            ice_path.write_text(ICE_FIXTURE, encoding="utf-8")
            changed = apply_webrtc_patch.apply_patch(src)
            self.assertEqual([apply_webrtc_patch.RTC_ICE_CANDIDATE_CC], changed)
            self.assertIn("fingerprint-webrtc-ip", ice_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
