#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_CHROMIUM_SRC = Path("/Users/chun/Projects/browser-source/browseforge-chromium/src")
AUDIO_BUFFER_CC = Path("third_party/blink/renderer/modules/webaudio/audio_buffer.cc")
ANALYSER_NODE_CC = Path("third_party/blink/renderer/modules/webaudio/analyser_node.cc")

COMMAND_LINE_INCLUDE = '#include "base/command_line.h"\n'
SPAN_INCLUDE = '#include "base/containers/span.h"\n'
AUDIO_BUFFER_INCLUDE_ANCHOR = '#include "base/compiler_specific.h"\n'
ANALYSER_INCLUDE_ANCHOR = '#include "third_party/blink/renderer/bindings/modules/v8/v8_analyser_options.h"\n'
AUDIO_BUFFER_NAMESPACE_ANCHOR = "namespace {\n\n"
ANALYSER_NAMESPACE_ANCHOR = "namespace blink {\n\n"

AUDIO_NOISE_HELPER = '''uint32_t BrowseForgeAudioNoiseSeed() {\n  const std::string value = base::CommandLine::ForCurrentProcess()->GetSwitchValueASCII(\n      "fingerprint-audio-noise");\n  uint32_t seed = 0;\n  bool has_digit = false;\n  for (char c : value) {\n    if (c < '0' || c > '9') {\n      return 0;\n    }\n    has_digit = true;\n    seed = seed * 10u + static_cast<uint32_t>(c - '0');\n  }\n  return has_digit && seed != 0 ? seed : 0;\n}\n\nfloat BrowseForgeAudioNoiseDelta(uint32_t seed, uint32_t index) {\n  uint32_t x = seed ^ (index * 747796405u);\n  x ^= x >> 16;\n  x *= 2891336453u;\n  x ^= x >> 13;\n  const int32_t centered = static_cast<int32_t>(x % 2001u) - 1000;\n  return static_cast<float>(centered) * 0.000000001f;\n}\n\nvoid BrowseForgeApplyAudioNoise(base::span<float> samples) {\n  const uint32_t seed = BrowseForgeAudioNoiseSeed();\n  if (!seed) {\n    return;\n  }\n  for (size_t i = 0; i < samples.size(); ++i) {\n    samples[i] += BrowseForgeAudioNoiseDelta(seed, static_cast<uint32_t>(i));\n  }\n}\n\n[[maybe_unused]] void BrowseForgeApplyAudioByteNoise(base::span<uint8_t> samples) {\n  const uint32_t seed = BrowseForgeAudioNoiseSeed();\n  if (!seed) {\n    return;\n  }\n  for (size_t i = 0; i < samples.size(); ++i) {\n    const int delta = BrowseForgeAudioNoiseDelta(seed, static_cast<uint32_t>(i)) > 0 ? 1 : -1;\n    const int value = static_cast<int>(samples[i]) + delta;\n    samples[i] = static_cast<uint8_t>(value < 0 ? 0 : value > 255 ? 255 : value);\n  }\n}\n\n'''

ORIGINAL_GET_CHANNEL = '''NotShared<DOMFloat32Array> AudioBuffer::getChannelData(unsigned channel_index) {\n  if (channel_index >= channels_.size()) {\n    return NotShared<DOMFloat32Array>(nullptr);\n  }\n\n  return NotShared<DOMFloat32Array>(channels_[channel_index].Get());\n}\n'''
PATCHED_GET_CHANNEL = '''NotShared<DOMFloat32Array> AudioBuffer::getChannelData(unsigned channel_index) {\n  if (channel_index >= channels_.size()) {\n    return NotShared<DOMFloat32Array>(nullptr);\n  }\n\n  DOMFloat32Array* channel_data = channels_[channel_index].Get();\n  if (!BrowseForgeAudioNoiseSeed()) {\n    return NotShared<DOMFloat32Array>(channel_data);\n  }\n\n  DOMFloat32Array* noisy_data = DOMFloat32Array::CreateOrNull(channel_data->length());\n  if (!noisy_data) {\n    return NotShared<DOMFloat32Array>(channel_data);\n  }\n  noisy_data->AsSpan().copy_from(channel_data->AsSpan());\n  BrowseForgeApplyAudioNoise(noisy_data->AsSpan());\n  return NotShared<DOMFloat32Array>(noisy_data);\n}\n'''

ORIGINAL_COPY_FROM = '''  dst.first(count).copy_from(src.subspan(buffer_offset, count));\n}\n'''
PATCHED_COPY_FROM = '''  dst.first(count).copy_from(src.subspan(buffer_offset, count));\n  BrowseForgeApplyAudioNoise(dst.first(count));\n}\n'''

ORIGINAL_FLOAT_FREQ = '''void AnalyserNode::getFloatFrequencyData(NotShared<DOMFloat32Array> array) {\n  GetAnalyserHandler().GetFloatFrequencyData(array.Get(),\n                                             context()->currentTime());\n}\n'''
PATCHED_FLOAT_FREQ = '''void AnalyserNode::getFloatFrequencyData(NotShared<DOMFloat32Array> array) {\n  GetAnalyserHandler().GetFloatFrequencyData(array.Get(),\n                                             context()->currentTime());\n  BrowseForgeApplyAudioNoise(array->AsSpan());\n}\n'''
ORIGINAL_BYTE_FREQ = '''void AnalyserNode::getByteFrequencyData(NotShared<DOMUint8Array> array) {\n  GetAnalyserHandler().GetByteFrequencyData(array.Get(),\n                                            context()->currentTime());\n}\n'''
PATCHED_BYTE_FREQ = '''void AnalyserNode::getByteFrequencyData(NotShared<DOMUint8Array> array) {\n  GetAnalyserHandler().GetByteFrequencyData(array.Get(),\n                                            context()->currentTime());\n  BrowseForgeApplyAudioByteNoise(array->AsSpan());\n}\n'''
ORIGINAL_FLOAT_TIME = '''void AnalyserNode::getFloatTimeDomainData(NotShared<DOMFloat32Array> array) {\n  GetAnalyserHandler().GetFloatTimeDomainData(array.Get());\n}\n'''
PATCHED_FLOAT_TIME = '''void AnalyserNode::getFloatTimeDomainData(NotShared<DOMFloat32Array> array) {\n  GetAnalyserHandler().GetFloatTimeDomainData(array.Get());\n  BrowseForgeApplyAudioNoise(array->AsSpan());\n}\n'''
ORIGINAL_BYTE_TIME = '''void AnalyserNode::getByteTimeDomainData(NotShared<DOMUint8Array> array) {\n  GetAnalyserHandler().GetByteTimeDomainData(array.Get());\n}\n'''
PATCHED_BYTE_TIME = '''void AnalyserNode::getByteTimeDomainData(NotShared<DOMUint8Array> array) {\n  GetAnalyserHandler().GetByteTimeDomainData(array.Get());\n  BrowseForgeApplyAudioByteNoise(array->AsSpan());\n}\n'''


def validate_chromium_src(src: Path) -> None:
    if not (src / ".git").exists():
        raise SystemExit(f"Chromium source checkout is not ready: {src}")
    for rel in (AUDIO_BUFFER_CC, ANALYSER_NODE_CC):
        if not (src / rel).is_file():
            raise SystemExit(f"Chromium WebAudio source file is missing: {src / rel}")


def ensure_include(text: str, anchor: str, include: str, label: str) -> str:
    if include in text:
        return text
    if anchor not in text:
        raise SystemExit(f"{label} include anchor not found")
    return text.replace(anchor, anchor + include, 1)


def patch_audio_buffer(text: str) -> str:
    patched = ensure_include(text, AUDIO_BUFFER_INCLUDE_ANCHOR, COMMAND_LINE_INCLUDE, "audio_buffer.cc")
    if "BrowseForgeAudioNoiseSeed" not in patched:
        if AUDIO_BUFFER_NAMESPACE_ANCHOR not in patched:
            raise SystemExit("audio_buffer.cc namespace anchor not found")
        patched = patched.replace(AUDIO_BUFFER_NAMESPACE_ANCHOR, AUDIO_BUFFER_NAMESPACE_ANCHOR + AUDIO_NOISE_HELPER, 1)
    patched = patched.replace(
        "\nvoid BrowseForgeApplyAudioByteNoise(base::span<uint8_t> samples)",
        "\n[[maybe_unused]] void BrowseForgeApplyAudioByteNoise(base::span<uint8_t> samples)",
    )
    for original, replacement, label in [
        (ORIGINAL_GET_CHANNEL, PATCHED_GET_CHANNEL, "AudioBuffer::getChannelData"),
        (ORIGINAL_COPY_FROM, PATCHED_COPY_FROM, "AudioBuffer::copyFromChannel"),
    ]:
        if replacement in patched:
            continue
        if original not in patched:
            raise SystemExit(f"{label} anchor not found")
        patched = patched.replace(original, replacement, 1)
    return patched


def patch_analyser(text: str) -> str:
    patched = ensure_include(text, ANALYSER_INCLUDE_ANCHOR, SPAN_INCLUDE, "analyser_node.cc")
    patched = ensure_include(patched, SPAN_INCLUDE, COMMAND_LINE_INCLUDE, "analyser_node.cc")
    if "BrowseForgeAudioNoiseSeed" not in patched:
        if ANALYSER_NAMESPACE_ANCHOR not in patched:
            raise SystemExit("analyser_node.cc namespace anchor not found")
        patched = patched.replace(ANALYSER_NAMESPACE_ANCHOR, ANALYSER_NAMESPACE_ANCHOR + "namespace {\n\n" + AUDIO_NOISE_HELPER + "}  // namespace\n\n", 1)
    patched = patched.replace(
        "\nvoid BrowseForgeApplyAudioByteNoise(base::span<uint8_t> samples)",
        "\n[[maybe_unused]] void BrowseForgeApplyAudioByteNoise(base::span<uint8_t> samples)",
    )
    for original, replacement, label in [
        (ORIGINAL_FLOAT_FREQ, PATCHED_FLOAT_FREQ, "AnalyserNode::getFloatFrequencyData"),
        (ORIGINAL_BYTE_FREQ, PATCHED_BYTE_FREQ, "AnalyserNode::getByteFrequencyData"),
        (ORIGINAL_FLOAT_TIME, PATCHED_FLOAT_TIME, "AnalyserNode::getFloatTimeDomainData"),
        (ORIGINAL_BYTE_TIME, PATCHED_BYTE_TIME, "AnalyserNode::getByteTimeDomainData"),
    ]:
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
    changed: list[Path] = []
    buffer_path = src / AUDIO_BUFFER_CC
    analyser_path = src / ANALYSER_NODE_CC
    if write_if_changed(buffer_path, patch_audio_buffer(buffer_path.read_text(encoding="utf-8"))):
        changed.append(AUDIO_BUFFER_CC)
    if write_if_changed(analyser_path, patch_analyser(analyser_path.read_text(encoding="utf-8"))):
        changed.append(ANALYSER_NODE_CC)
    return changed or [AUDIO_BUFFER_CC, ANALYSER_NODE_CC]


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply BrowseForge WebAudio fingerprint noise source patches")
    parser.add_argument("--chromium-src", type=Path, default=DEFAULT_CHROMIUM_SRC)
    parser.add_argument("--check", action="store_true", help="validate checkout and patch anchors without writing")
    args = parser.parse_args()

    src = args.chromium_src.resolve()
    validate_chromium_src(src)
    if args.check:
        patch_audio_buffer((src / AUDIO_BUFFER_CC).read_text(encoding="utf-8"))
        patch_analyser((src / ANALYSER_NODE_CC).read_text(encoding="utf-8"))
        print(f"ready: {src / AUDIO_BUFFER_CC}")
        print(f"ready: {src / ANALYSER_NODE_CC}")
        return
    for path in apply_patch(src):
        print(path.as_posix())


if __name__ == "__main__":
    main()
