#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_CHROMIUM_SRC = Path("/Users/chun/Projects/browser-source/browseforge-chromium/src")
RTC_ICE_CANDIDATE_CC = Path("third_party/blink/renderer/modules/peerconnection/rtc_ice_candidate.cc")

COMMAND_LINE_INCLUDE = '#include "base/command_line.h"\n'
INCLUDE_ANCHOR = '#include <utility>\n\n'
NAMESPACE_ANCHOR = "namespace blink {\n\n"

WEBRTC_HELPER = '''namespace {\n\nString BrowseForgeWebRTCIPOverride() {\n  const std::string ip = base::CommandLine::ForCurrentProcess()->GetSwitchValueASCII(\n      "fingerprint-webrtc-ip");\n  if (ip.empty() || ip == "auto" || ip.size() > 64) {\n    return String();\n  }\n  bool has_digit = false;\n  for (char c : ip) {\n    const bool valid = (c >= '0' && c <= '9') || (c >= 'A' && c <= 'F') ||\n                       (c >= 'a' && c <= 'f') || c == '.' || c == ':';\n    if (!valid) {\n      return String();\n    }\n    has_digit = has_digit || (c >= '0' && c <= '9');\n  }\n  return has_digit ? String::FromUTF8(ip) : String();\n}\n\nString BrowseForgeWebRTCCandidateOverride(const String& candidate,\n                                          const String& address) {\n  String ip = BrowseForgeWebRTCIPOverride();\n  if (ip.empty() || address.empty()) {\n    return candidate;\n  }\n  return candidate.Replace(address, ip);\n}\n\n}  // namespace\n\n'''

ORIGINAL_CANDIDATE = '''String RTCIceCandidate::candidate() const {\n  return platform_candidate_->Candidate();\n}\n'''
PATCHED_CANDIDATE = '''String RTCIceCandidate::candidate() const {\n  return BrowseForgeWebRTCCandidateOverride(platform_candidate_->Candidate(),\n                                            platform_candidate_->Address());\n}\n'''

ORIGINAL_ADDRESS = '''String RTCIceCandidate::address() const {\n  return platform_candidate_->Address();\n}\n'''
PATCHED_ADDRESS = '''String RTCIceCandidate::address() const {\n  String ip = BrowseForgeWebRTCIPOverride();\n  return ip.empty() ? platform_candidate_->Address() : ip;\n}\n'''

ORIGINAL_RELATED_ADDRESS = '''String RTCIceCandidate::relatedAddress() const {\n  return platform_candidate_->RelatedAddress();\n}\n'''
PATCHED_RELATED_ADDRESS = '''String RTCIceCandidate::relatedAddress() const {\n  String ip = BrowseForgeWebRTCIPOverride();\n  return ip.empty() ? platform_candidate_->RelatedAddress() : ip;\n}\n'''

ORIGINAL_JSON = '''  result.AddString("candidate", platform_candidate_->Candidate());\n'''
PATCHED_JSON = '''  result.AddString("candidate", candidate());\n'''


def validate_chromium_src(src: Path) -> None:
    if not (src / ".git").exists():
        raise SystemExit(f"Chromium source checkout is not ready: {src}")
    if not (src / RTC_ICE_CANDIDATE_CC).is_file():
        raise SystemExit(f"Chromium ICE candidate source file is missing: {src / RTC_ICE_CANDIDATE_CC}")


def ensure_include(text: str) -> str:
    if COMMAND_LINE_INCLUDE in text:
        return text
    if INCLUDE_ANCHOR not in text:
        raise SystemExit("rtc_ice_candidate.cc include anchor not found")
    return text.replace(INCLUDE_ANCHOR, INCLUDE_ANCHOR + COMMAND_LINE_INCLUDE, 1)


def patch_webrtc(text: str) -> str:
    patched = ensure_include(text)
    if "BrowseForgeWebRTCIPOverride" not in patched:
        if NAMESPACE_ANCHOR not in patched:
            raise SystemExit("rtc_ice_candidate.cc namespace anchor not found")
        patched = patched.replace(NAMESPACE_ANCHOR, NAMESPACE_ANCHOR + WEBRTC_HELPER, 1)
    replacements = [
        (ORIGINAL_CANDIDATE, PATCHED_CANDIDATE, "RTCIceCandidate::candidate"),
        (ORIGINAL_ADDRESS, PATCHED_ADDRESS, "RTCIceCandidate::address"),
        (ORIGINAL_RELATED_ADDRESS, PATCHED_RELATED_ADDRESS, "RTCIceCandidate::relatedAddress"),
        (ORIGINAL_JSON, PATCHED_JSON, "RTCIceCandidate::toJSONForBinding candidate"),
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
    path = src / RTC_ICE_CANDIDATE_CC
    write_if_changed(path, patch_webrtc(path.read_text(encoding="utf-8")))
    return [RTC_ICE_CANDIDATE_CC]


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply BrowseForge WebRTC ICE candidate source patch")
    parser.add_argument("--chromium-src", type=Path, default=DEFAULT_CHROMIUM_SRC)
    parser.add_argument("--check", action="store_true", help="validate checkout and patch anchors without writing")
    args = parser.parse_args()

    src = args.chromium_src.resolve()
    validate_chromium_src(src)
    if args.check:
        patch_webrtc((src / RTC_ICE_CANDIDATE_CC).read_text(encoding="utf-8"))
        print(f"ready: {src / RTC_ICE_CANDIDATE_CC}")
        return
    for path in apply_patch(src):
        print(path.as_posix())


if __name__ == "__main__":
    main()
