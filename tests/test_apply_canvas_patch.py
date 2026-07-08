from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "apply_canvas_patch.py"

spec = importlib.util.spec_from_file_location("apply_canvas_patch", SCRIPT)
assert spec and spec.loader
apply_canvas_patch = importlib.util.module_from_spec(spec)
sys.modules["apply_canvas_patch"] = apply_canvas_patch
spec.loader.exec_module(apply_canvas_patch)

BASE_CONTEXT_FIXTURE = '''#include "third_party/blink/renderer/modules/canvas/canvas2d/base_rendering_context_2d.h"

#include <cmath>
#include <cstdint>


#include "base/check.h"
#include "third_party/blink/renderer/core/html/canvas/image_data.h"

namespace blink {

namespace {


bool IsContextProviderValid() {
  return true;
}

}  // namespace

ImageData* BaseRenderingContext2D::getImageDataInternal(
    int sx,
    int sy,
    int sw,
    int sh,
    ImageDataSettings* image_data_settings,
    ExceptionState& exception_state) {
  ImageData* image_data = MakeGarbageCollected<ImageData>();
  scoped_refptr<StaticBitmapImage> snapshot = GetImage();
  if (snapshot) {
    SkPixmap image_data_pixmap = image_data->GetSkPixmap();
    const bool read_pixels_successful =
        snapshot->PaintImageForCurrentFrame().readPixels(
            image_data_pixmap.info(), image_data_pixmap.writable_addr(),
            image_data_pixmap.rowBytes(), sx, sy);
    if (!read_pixels_successful) {
      SkIRect bounds =
          snapshot->PaintImageForCurrentFrame().GetSkImageInfo().bounds();
      DCHECK(!bounds.intersect(SkIRect::MakeXYWH(sx, sy, sw, sh)));
    }
  }

  return image_data;
}
'''

IMAGE_DATA_BUFFER_FIXTURE = '''#include "third_party/blink/renderer/platform/graphics/image_data_buffer.h"

#include "base/compiler_specific.h"
#include "base/memory/ptr_util.h"
#include "third_party/blink/renderer/platform/image-encoders/image_encoder_utils.h"
#include "third_party/blink/renderer/platform/wtf/text/base64.h"
#include "third_party/blink/renderer/platform/wtf/text/strcat.h"
#include "third_party/skia/include/core/SkImage.h"
#include "third_party/skia/include/core/SkSurface.h"
#include "ui/gfx/skia_span_util.h"

namespace blink {

bool ImageDataBuffer::EncodeImage(const ImageEncodingMimeType mime_type,
                                  const double& quality,
                                  Vector<unsigned char>* encoded_image) const {
  return ImageEncoder::Encode(encoded_image, pixmap_, mime_type, quality);
}

String ImageDataBuffer::ToDataURL(const ImageEncodingMimeType mime_type,
                                  const double& quality) const {
  DCHECK(is_valid_);
  Vector<unsigned char> result;
  if (!ImageEncoder::Encode(&result, pixmap_, mime_type, quality)) {
    return "data:,";
  }
  return StrCat({"data:", ImageEncoderUtils::MimeTypeName(mime_type),
                 ";base64,", Base64Encode(result)});
}

}  // namespace blink
'''

IMAGE_DATA_BUFFER_HEADER_FIXTURE = '''#ifndef THIRD_PARTY_BLINK_RENDERER_PLATFORM_GRAPHICS_IMAGE_DATA_BUFFER_H_
#define THIRD_PARTY_BLINK_RENDERER_PLATFORM_GRAPHICS_IMAGE_DATA_BUFFER_H_
namespace blink {
class ImageDataBuffer {
 public:
  String ToDataURL(const ImageEncodingMimeType mime_type,
                   const double& quality) const;
  bool EncodeImage(const ImageEncodingMimeType mime_type,
                   const double& quality,
                   Vector<unsigned char>* encoded_image) const;
};
}  // namespace blink
#endif
'''


class ApplyCanvasPatchTests(unittest.TestCase):
    def test_patches_get_image_data_readback(self) -> None:
        patched = apply_canvas_patch.patch_base_context(BASE_CONTEXT_FIXTURE)
        self.assertIn('#include "base/command_line.h"', patched)
        self.assertIn('"fingerprint-canvas-noise"', patched)
        self.assertIn('BrowseForgeApplyCanvasNoise(&image_data_pixmap)', patched)

    def test_patches_canvas_encoding_readback(self) -> None:
        patched = apply_canvas_patch.patch_image_data_buffer_cc(IMAGE_DATA_BUFFER_FIXTURE)
        self.assertIn('#include <cstring>', patched)
        self.assertIn('#include "base/command_line.h"', patched)
        self.assertIn('BrowseForgeMakeNoisyCanvasPixmap', patched)
        self.assertIn('EncodeImage(mime_type, quality, &result)', patched)
        self.assertIn("UNSAFE_TODO(static_cast<uint8_t*>(pixmap->writable_addr())", patched)
        self.assertIn("UNSAFE_TODO(std::memcpy(dest_row, source_row,", patched)

    def test_patch_is_idempotent(self) -> None:
        base_once = apply_canvas_patch.patch_base_context(BASE_CONTEXT_FIXTURE)
        self.assertEqual(base_once, apply_canvas_patch.patch_base_context(base_once))
        buffer_once = apply_canvas_patch.patch_image_data_buffer_cc(IMAGE_DATA_BUFFER_FIXTURE)
        self.assertEqual(buffer_once, apply_canvas_patch.patch_image_data_buffer_cc(buffer_once))

    def test_apply_patch_updates_external_checkout_shape(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            src = Path(td) / "src"
            base_path = src / apply_canvas_patch.BASE_RENDERING_CONTEXT_2D_CC
            buffer_path = src / apply_canvas_patch.IMAGE_DATA_BUFFER_CC
            header_path = src / apply_canvas_patch.IMAGE_DATA_BUFFER_H
            base_path.parent.mkdir(parents=True)
            buffer_path.parent.mkdir(parents=True)
            (src / ".git").mkdir()
            base_path.write_text(BASE_CONTEXT_FIXTURE, encoding="utf-8")
            buffer_path.write_text(IMAGE_DATA_BUFFER_FIXTURE, encoding="utf-8")
            header_path.write_text(IMAGE_DATA_BUFFER_HEADER_FIXTURE, encoding="utf-8")
            changed = apply_canvas_patch.apply_patch(src)
            self.assertIn(apply_canvas_patch.BASE_RENDERING_CONTEXT_2D_CC, changed)
            self.assertIn(apply_canvas_patch.IMAGE_DATA_BUFFER_CC, changed)
            self.assertIn("fingerprint-canvas-noise", base_path.read_text(encoding="utf-8"))
            self.assertIn("fingerprint-canvas-noise", buffer_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
