from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "apply_audio_patch.py"

spec = importlib.util.spec_from_file_location("apply_audio_patch", SCRIPT)
assert spec and spec.loader
apply_audio_patch = importlib.util.module_from_spec(spec)
sys.modules["apply_audio_patch"] = apply_audio_patch
spec.loader.exec_module(apply_audio_patch)

AUDIO_BUFFER_FIXTURE = '''#include "third_party/blink/renderer/modules/webaudio/audio_buffer.h"

#include <memory>

#include "base/compiler_specific.h"
#include "base/containers/span.h"

namespace blink {

namespace {

DOMFloat32Array* CreateFloat32ArrayOrNull(
    uint32_t length,
    AudioBuffer::InitializationPolicy policy) {
  return DOMFloat32Array::CreateOrNull(length);
}

}  // namespace

NotShared<DOMFloat32Array> AudioBuffer::getChannelData(unsigned channel_index) {
  if (channel_index >= channels_.size()) {
    return NotShared<DOMFloat32Array>(nullptr);
  }

  return NotShared<DOMFloat32Array>(channels_[channel_index].Get());
}

void AudioBuffer::copyFromChannel(NotShared<DOMFloat32Array> destination,
                                  int32_t channel_number,
                                  size_t buffer_offset,
                                  ExceptionState& exception_state) {
  base::span<const float> src = channels_[channel_number].Get()->AsSpan();
  base::span<float> dst = destination->AsSpan();
  size_t count = std::min(dst.size(), src.size() - buffer_offset);

  DCHECK(src.data());
  DCHECK(dst.data());

  dst.first(count).copy_from(src.subspan(buffer_offset, count));
}

}  // namespace blink
'''

ANALYSER_FIXTURE = '''#include "third_party/blink/renderer/modules/webaudio/analyser_node.h"

#include "third_party/blink/renderer/bindings/modules/v8/v8_analyser_options.h"
#include "third_party/blink/renderer/modules/webaudio/analyser_handler.h"

namespace blink {

void AnalyserNode::getFloatFrequencyData(NotShared<DOMFloat32Array> array) {
  GetAnalyserHandler().GetFloatFrequencyData(array.Get(),
                                             context()->currentTime());
}

void AnalyserNode::getByteFrequencyData(NotShared<DOMUint8Array> array) {
  GetAnalyserHandler().GetByteFrequencyData(array.Get(),
                                            context()->currentTime());
}

void AnalyserNode::getFloatTimeDomainData(NotShared<DOMFloat32Array> array) {
  GetAnalyserHandler().GetFloatTimeDomainData(array.Get());
}

void AnalyserNode::getByteTimeDomainData(NotShared<DOMUint8Array> array) {
  GetAnalyserHandler().GetByteTimeDomainData(array.Get());
}

}  // namespace blink
'''


class ApplyAudioPatchTests(unittest.TestCase):
    def test_patches_audio_buffer_outputs(self) -> None:
        patched = apply_audio_patch.patch_audio_buffer(AUDIO_BUFFER_FIXTURE)
        self.assertIn('#include "base/command_line.h"', patched)
        self.assertIn('"fingerprint-audio-noise"', patched)
        self.assertIn('DOMFloat32Array::CreateOrNull(channel_data->length())', patched)
        self.assertIn('BrowseForgeApplyAudioNoise(noisy_data->AsSpan())', patched)
        self.assertIn('BrowseForgeApplyAudioNoise(dst.first(count), static_cast<uint32_t>(buffer_offset))', patched)
        self.assertIn('start_index + static_cast<uint32_t>(i)', patched)

    def test_patches_analyser_outputs(self) -> None:
        patched = apply_audio_patch.patch_analyser(ANALYSER_FIXTURE)
        self.assertIn('#include "base/command_line.h"', patched)
        self.assertIn('#include "base/containers/span.h"', patched)
        self.assertIn('BrowseForgeApplyAudioNoise(array->AsSpan())', patched)
        self.assertIn('BrowseForgeApplyAudioByteNoise(array->AsSpan())', patched)
        self.assertIn('[[maybe_unused]] void BrowseForgeApplyAudioByteNoise', patched)
        self.assertIn('BrowseForgeApplyAudioByteNoise(base::span<uint8_t> samples, uint32_t start_index = 0)', patched)

    def test_patch_is_idempotent(self) -> None:
        patched_buffer_once = apply_audio_patch.patch_audio_buffer(AUDIO_BUFFER_FIXTURE)
        patched_buffer_twice = apply_audio_patch.patch_audio_buffer(patched_buffer_once)
        self.assertEqual(patched_buffer_once, patched_buffer_twice)
        patched_analyser_once = apply_audio_patch.patch_analyser(ANALYSER_FIXTURE)
        patched_analyser_twice = apply_audio_patch.patch_analyser(patched_analyser_once)
        self.assertEqual(patched_analyser_once, patched_analyser_twice)


    def test_patch_upgrades_legacy_audio_offset_noise(self) -> None:
        patched = apply_audio_patch.patch_audio_buffer(AUDIO_BUFFER_FIXTURE)
        legacy = patched.replace(
            "void BrowseForgeApplyAudioNoise(base::span<float> samples, uint32_t start_index = 0)",
            "void BrowseForgeApplyAudioNoise(base::span<float> samples)",
        ).replace(
            "BrowseForgeAudioNoiseDelta(seed, start_index + static_cast<uint32_t>(i))",
            "BrowseForgeAudioNoiseDelta(seed, static_cast<uint32_t>(i))",
        ).replace(
            "BrowseForgeApplyAudioNoise(dst.first(count), static_cast<uint32_t>(buffer_offset));",
            "BrowseForgeApplyAudioNoise(dst.first(count));",
        )

        upgraded = apply_audio_patch.patch_audio_buffer(legacy)

        self.assertIn("void BrowseForgeApplyAudioNoise(base::span<float> samples, uint32_t start_index = 0)", upgraded)
        self.assertIn("BrowseForgeAudioNoiseDelta(seed, start_index + static_cast<uint32_t>(i))", upgraded)
        self.assertIn("BrowseForgeApplyAudioNoise(dst.first(count), static_cast<uint32_t>(buffer_offset));", upgraded)

    def test_apply_patch_updates_external_checkout_shape(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "src"
            buffer_path = src / apply_audio_patch.AUDIO_BUFFER_CC
            analyser_path = src / apply_audio_patch.ANALYSER_NODE_CC
            buffer_path.parent.mkdir(parents=True)
            analyser_path.parent.mkdir(parents=True, exist_ok=True)
            (src / ".git").mkdir()
            buffer_path.write_text(AUDIO_BUFFER_FIXTURE, encoding="utf-8")
            analyser_path.write_text(ANALYSER_FIXTURE, encoding="utf-8")
            changed = apply_audio_patch.apply_patch(src)
            self.assertEqual(
                [apply_audio_patch.AUDIO_BUFFER_CC, apply_audio_patch.ANALYSER_NODE_CC],
                changed,
            )
            self.assertIn("fingerprint-audio-noise", buffer_path.read_text(encoding="utf-8"))
            self.assertIn("fingerprint-audio-noise", analyser_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
