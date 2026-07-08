#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

DEFAULT_CHROMIUM_SRC = Path("/Users/chun/Projects/browser-source/browseforge-chromium/src")
BASE_RENDERING_CONTEXT_2D_CC = Path("third_party/blink/renderer/modules/canvas/canvas2d/base_rendering_context_2d.cc")
IMAGE_DATA_BUFFER_CC = Path("third_party/blink/renderer/platform/graphics/image_data_buffer.cc")
IMAGE_DATA_BUFFER_H = Path("third_party/blink/renderer/platform/graphics/image_data_buffer.h")

COMMAND_LINE_INCLUDE = '#include "base/command_line.h"\n'
CSTRING_INCLUDE = '#include <cstring>\n'
BASE_INCLUDE_ANCHOR = '#include "base/check.h"\n'
BASE_NAMESPACE_ANCHOR = 'namespace {\n\n\n'
BUFFER_INCLUDE_ANCHOR = '#include "third_party/blink/renderer/platform/graphics/image_data_buffer.h"\n\n'
BUFFER_NAMESPACE_ANCHOR = 'namespace blink {\n\n'
HEADER_METHOD_ANCHOR = '  bool EncodeImage(const ImageEncodingMimeType mime_type,\n                   const double& quality,\n                   Vector<unsigned char>* encoded_image) const;\n'

CANVAS_NOISE_HELPER = '''uint32_t BrowseForgeCanvasNoiseSeed() {\n  const std::string value = base::CommandLine::ForCurrentProcess()->GetSwitchValueASCII(\n      "fingerprint-canvas-noise");\n  uint32_t seed = 0;\n  bool has_digit = false;\n  for (char c : value) {\n    if (c < '0' || c > '9') {\n      return 0;\n    }\n    has_digit = true;\n    seed = seed * 10u + static_cast<uint32_t>(c - '0');\n  }\n  return has_digit && seed != 0 ? seed : 0;\n}\n\nint BrowseForgeCanvasNoiseDelta(uint32_t seed, uint32_t index) {\n  uint32_t x = seed ^ (index * 747796405u);\n  x ^= x >> 16;\n  x *= 2891336453u;\n  x ^= x >> 13;\n  return static_cast<int>(x % 3u) - 1;\n}\n\nvoid BrowseForgeApplyCanvasNoise(SkPixmap* pixmap) {\n  const uint32_t seed = BrowseForgeCanvasNoiseSeed();\n  if (!seed || !pixmap || !pixmap->writable_addr() ||\n      pixmap->info().bytesPerPixel() < 4) {\n    return;\n  }\n\n  const int width = pixmap->width();\n  const int height = pixmap->height();\n  const size_t bytes_per_pixel = pixmap->info().bytesPerPixel();\n  for (int y = 0; y < height; ++y) {\n    uint8_t* row = UNSAFE_TODO(static_cast<uint8_t*>(pixmap->writable_addr()) +\n                               static_cast<size_t>(y) * pixmap->rowBytes());\n    for (int x = 0; x < width; ++x) {\n      uint8_t* pixel = UNSAFE_TODO(row + static_cast<size_t>(x) * bytes_per_pixel);\n      for (int channel = 0; channel < 3; ++channel) {\n        const uint32_t noise_index =\n            static_cast<uint32_t>((y * width + x) * 3 + channel);\n        const int value = static_cast<int>(UNSAFE_TODO(pixel[channel])) +\n                          BrowseForgeCanvasNoiseDelta(seed, noise_index);\n        UNSAFE_TODO(pixel[channel]) =\n            static_cast<uint8_t>(value < 0 ? 0 : value > 255 ? 255 : value);\n      }\n    }\n  }\n}\n\n'''

BUFFER_NOISE_HELPER = CANVAS_NOISE_HELPER + '''bool BrowseForgeMakeNoisyCanvasPixmap(const SkPixmap& source,\n                                      SkPixmap* destination,\n                                      sk_sp<SkData>* data) {\n  const uint32_t seed = BrowseForgeCanvasNoiseSeed();\n  if (!seed || !source.addr() || source.info().bytesPerPixel() < 4) {\n    return false;\n  }\n\n  const size_t size = source.info().computeByteSize(source.rowBytes());\n  if (SkImageInfo::ByteSizeOverflowed(size)) {\n    return false;\n  }\n\n  *data = SkData::MakeUninitialized(size);\n  *destination = SkPixmap(source.info(), (*data)->writable_data(), source.rowBytes());\n  for (int y = 0; y < source.height(); ++y) {\n    const uint8_t* source_row = UNSAFE_TODO(static_cast<const uint8_t*>(source.addr()) +\n                                            static_cast<size_t>(y) * source.rowBytes());\n    uint8_t* dest_row = UNSAFE_TODO(static_cast<uint8_t*>(destination->writable_addr()) +\n                                    static_cast<size_t>(y) * destination->rowBytes());\n    UNSAFE_TODO(std::memcpy(dest_row, source_row,\n                            source.width() * source.info().bytesPerPixel()));\n  }\n  BrowseForgeApplyCanvasNoise(destination);\n  return true;\n}\n\n'''

ORIGINAL_GET_IMAGE_DATA_RETURN = '''    const bool read_pixels_successful =\n        snapshot->PaintImageForCurrentFrame().readPixels(\n            image_data_pixmap.info(), image_data_pixmap.writable_addr(),\n            image_data_pixmap.rowBytes(), sx, sy);\n    if (!read_pixels_successful) {\n      SkIRect bounds =\n          snapshot->PaintImageForCurrentFrame().GetSkImageInfo().bounds();\n      DCHECK(!bounds.intersect(SkIRect::MakeXYWH(sx, sy, sw, sh)));\n    }\n  }\n\n  return image_data;\n}\n'''
PATCHED_GET_IMAGE_DATA_RETURN = '''    const bool read_pixels_successful =\n        snapshot->PaintImageForCurrentFrame().readPixels(\n            image_data_pixmap.info(), image_data_pixmap.writable_addr(),\n            image_data_pixmap.rowBytes(), sx, sy);\n    if (read_pixels_successful) {\n      BrowseForgeApplyCanvasNoise(&image_data_pixmap);\n    } else {\n      SkIRect bounds =\n          snapshot->PaintImageForCurrentFrame().GetSkImageInfo().bounds();\n      DCHECK(!bounds.intersect(SkIRect::MakeXYWH(sx, sy, sw, sh)));\n    }\n  }\n\n  return image_data;\n}\n'''

ORIGINAL_ENCODE = '''bool ImageDataBuffer::EncodeImage(const ImageEncodingMimeType mime_type,\n                                  const double& quality,\n                                  Vector<unsigned char>* encoded_image) const {\n  return ImageEncoder::Encode(encoded_image, pixmap_, mime_type, quality);\n}\n'''
PATCHED_ENCODE = '''bool ImageDataBuffer::EncodeImage(const ImageEncodingMimeType mime_type,\n                                  const double& quality,\n                                  Vector<unsigned char>* encoded_image) const {\n  SkPixmap noisy_pixmap;\n  sk_sp<SkData> noisy_data;\n  if (BrowseForgeMakeNoisyCanvasPixmap(pixmap_, &noisy_pixmap, &noisy_data)) {\n    return ImageEncoder::Encode(encoded_image, noisy_pixmap, mime_type, quality);\n  }\n  return ImageEncoder::Encode(encoded_image, pixmap_, mime_type, quality);\n}\n'''

ORIGINAL_TO_DATA_URL = '''String ImageDataBuffer::ToDataURL(const ImageEncodingMimeType mime_type,\n                                  const double& quality) const {\n  DCHECK(is_valid_);\n  Vector<unsigned char> result;\n  if (!ImageEncoder::Encode(&result, pixmap_, mime_type, quality)) {\n    return "data:,";\n  }\n  return StrCat({"data:", ImageEncoderUtils::MimeTypeName(mime_type),\n                 ";base64,", Base64Encode(result)});\n}\n'''
PATCHED_TO_DATA_URL = '''String ImageDataBuffer::ToDataURL(const ImageEncodingMimeType mime_type,\n                                  const double& quality) const {\n  DCHECK(is_valid_);\n  Vector<unsigned char> result;\n  if (!EncodeImage(mime_type, quality, &result)) {\n    return "data:,";\n  }\n  return StrCat({"data:", ImageEncoderUtils::MimeTypeName(mime_type),\n                 ";base64,", Base64Encode(result)});\n}\n'''

HEADER_PATCHED_METHOD = '''  bool EncodeImage(const ImageEncodingMimeType mime_type,\n                   const double& quality,\n                   Vector<unsigned char>* encoded_image) const;\n  String ToDataURLWithCanvasNoise(const ImageEncodingMimeType mime_type,\n                                  const double& quality) const;\n'''


def validate_chromium_src(src: Path) -> None:
    if not (src / ".git").exists():
        raise SystemExit(f"Chromium source checkout is not ready: {src}")
    for rel in (BASE_RENDERING_CONTEXT_2D_CC, IMAGE_DATA_BUFFER_CC, IMAGE_DATA_BUFFER_H):
        if not (src / rel).is_file():
            raise SystemExit(f"Chromium canvas source file is missing: {src / rel}")


def ensure_include(text: str, anchor: str, include: str, label: str) -> str:
    if include in text:
        return text
    if anchor not in text:
        raise SystemExit(f"{label} include anchor not found")
    return text.replace(anchor, anchor + include, 1)

def patch_base_context(text: str) -> str:
    patched = ensure_include(text, BASE_INCLUDE_ANCHOR, COMMAND_LINE_INCLUDE, "base_rendering_context_2d.cc")
    if "BrowseForgeCanvasNoiseSeed" not in patched:
        if BASE_NAMESPACE_ANCHOR not in patched:
            raise SystemExit("base_rendering_context_2d.cc namespace anchor not found")
        patched = patched.replace(BASE_NAMESPACE_ANCHOR, BASE_NAMESPACE_ANCHOR + CANVAS_NOISE_HELPER, 1)
    base_unsafe_migrations = [
        (
            "uint8_t* row = static_cast<uint8_t*>(pixmap->writable_addr()) +\n"
            "                   static_cast<size_t>(y) * pixmap->rowBytes();",
            "uint8_t* row = UNSAFE_TODO(static_cast<uint8_t*>(pixmap->writable_addr()) +\n"
            "                               static_cast<size_t>(y) * pixmap->rowBytes());",
        ),
        (
            "uint8_t* pixel = row + static_cast<size_t>(x) * bytes_per_pixel;",
            "uint8_t* pixel = UNSAFE_TODO(row + static_cast<size_t>(x) * bytes_per_pixel);",
        ),
        (
            "const int value = static_cast<int>(pixel[channel]) +\n"
            "                          BrowseForgeCanvasNoiseDelta(seed, noise_index);",
            "const int value = static_cast<int>(UNSAFE_TODO(pixel[channel])) +\n"
            "                          BrowseForgeCanvasNoiseDelta(seed, noise_index);",
        ),
        (
            "pixel[channel] = static_cast<uint8_t>(value < 0 ? 0 : value > 255 ? 255 : value);",
            "UNSAFE_TODO(pixel[channel]) =\n"
            "            static_cast<uint8_t>(value < 0 ? 0 : value > 255 ? 255 : value);",
        ),
    ]
    for original, replacement in base_unsafe_migrations:
        patched = patched.replace(original, replacement)
    if PATCHED_GET_IMAGE_DATA_RETURN not in patched:
        if ORIGINAL_GET_IMAGE_DATA_RETURN not in patched:
            raise SystemExit("BaseRenderingContext2D::getImageDataInternal anchor not found")
        patched = patched.replace(ORIGINAL_GET_IMAGE_DATA_RETURN, PATCHED_GET_IMAGE_DATA_RETURN, 1)
    return patched


def patch_image_data_buffer_cc(text: str) -> str:
    patched = ensure_include(text, BUFFER_INCLUDE_ANCHOR, CSTRING_INCLUDE, "image_data_buffer.cc")
    patched = ensure_include(patched, '#include "base/compiler_specific.h"\n', COMMAND_LINE_INCLUDE, "image_data_buffer.cc")
    if "BrowseForgeCanvasNoiseSeed" not in patched:
        if BUFFER_NAMESPACE_ANCHOR not in patched:
            raise SystemExit("image_data_buffer.cc namespace anchor not found")
        patched = patched.replace(BUFFER_NAMESPACE_ANCHOR, BUFFER_NAMESPACE_ANCHOR + "namespace {\n\n" + BUFFER_NOISE_HELPER + "}  // namespace\n\n", 1)
    unsafe_migrations = [
        (
            "uint8_t* row = static_cast<uint8_t*>(pixmap->writable_addr()) +\n"
            "                   static_cast<size_t>(y) * pixmap->rowBytes();",
            "uint8_t* row = UNSAFE_TODO(static_cast<uint8_t*>(pixmap->writable_addr()) +\n"
            "                               static_cast<size_t>(y) * pixmap->rowBytes());",
        ),
        (
            "uint8_t* pixel = row + static_cast<size_t>(x) * bytes_per_pixel;",
            "uint8_t* pixel = UNSAFE_TODO(row + static_cast<size_t>(x) * bytes_per_pixel);",
        ),
        (
            "const int value = static_cast<int>(pixel[channel]) +\n"
            "                          BrowseForgeCanvasNoiseDelta(seed, noise_index);",
            "const int value = static_cast<int>(UNSAFE_TODO(pixel[channel])) +\n"
            "                          BrowseForgeCanvasNoiseDelta(seed, noise_index);",
        ),
        (
            "pixel[channel] = static_cast<uint8_t>(value < 0 ? 0 : value > 255 ? 255 : value);",
            "UNSAFE_TODO(pixel[channel]) =\n"
            "            static_cast<uint8_t>(value < 0 ? 0 : value > 255 ? 255 : value);",
        ),
        (
            "UNSAFE_TODO(pixel[channel]) =\\n            static_cast<uint8_t>(value < 0 ? 0 : value > 255 ? 255 : value);",
            "UNSAFE_TODO(pixel[channel]) =\n"
            "            static_cast<uint8_t>(value < 0 ? 0 : value > 255 ? 255 : value);",
        ),
        (
            "const uint8_t* source_row = static_cast<const uint8_t*>(source.addr()) +\n"
            "                                static_cast<size_t>(y) * source.rowBytes();",
            "const uint8_t* source_row = UNSAFE_TODO(static_cast<const uint8_t*>(source.addr()) +\n"
            "                                            static_cast<size_t>(y) * source.rowBytes());",
        ),
        (
            "uint8_t* dest_row = static_cast<uint8_t*>(destination->writable_addr()) +\n"
            "                        static_cast<size_t>(y) * destination->rowBytes();",
            "uint8_t* dest_row = UNSAFE_TODO(static_cast<uint8_t*>(destination->writable_addr()) +\n"
            "                                    static_cast<size_t>(y) * destination->rowBytes());",
        ),
        (
            "std::memcpy(dest_row, source_row, source.width() * source.info().bytesPerPixel());",
            "UNSAFE_TODO(std::memcpy(dest_row, source_row,\n"
            "                            source.width() * source.info().bytesPerPixel()));",
        ),
        (
            "UNSAFE_TODO(std::memcpy(dest_row, source_row,\\n                            source.width() * source.info().bytesPerPixel()));",
            "UNSAFE_TODO(std::memcpy(dest_row, source_row,\n"
            "                            source.width() * source.info().bytesPerPixel()));",
        ),
    ]
    for original, replacement in unsafe_migrations:
        patched = patched.replace(original, replacement)
    for original, replacement, label in [
        (ORIGINAL_ENCODE, PATCHED_ENCODE, "ImageDataBuffer::EncodeImage"),
        (ORIGINAL_TO_DATA_URL, PATCHED_TO_DATA_URL, "ImageDataBuffer::ToDataURL"),
    ]:
        if replacement in patched:
            continue
        if original not in patched:
            raise SystemExit(f"{label} anchor not found")
        patched = patched.replace(original, replacement, 1)
    return patched


def patch_image_data_buffer_h(text: str) -> str:
    return text


def write_if_changed(path: Path, content: str) -> bool:
    original = path.read_text(encoding="utf-8")
    if content == original:
        return False
    path.write_text(content, encoding="utf-8")
    return True


def apply_patch(src: Path) -> list[Path]:
    validate_chromium_src(src)
    changes: list[Path] = []
    targets = [
        (BASE_RENDERING_CONTEXT_2D_CC, patch_base_context),
        (IMAGE_DATA_BUFFER_CC, patch_image_data_buffer_cc),
        (IMAGE_DATA_BUFFER_H, patch_image_data_buffer_h),
    ]
    for rel, patcher in targets:
        path = src / rel
        if write_if_changed(path, patcher(path.read_text(encoding="utf-8"))):
            changes.append(rel)
    return changes or [BASE_RENDERING_CONTEXT_2D_CC, IMAGE_DATA_BUFFER_CC]


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply BrowseForge canvas fingerprint noise source patches")
    parser.add_argument("--chromium-src", type=Path, default=DEFAULT_CHROMIUM_SRC)
    parser.add_argument("--check", action="store_true", help="validate checkout and patch anchors without writing")
    args = parser.parse_args()

    src = args.chromium_src.resolve()
    validate_chromium_src(src)
    if args.check:
        patch_base_context((src / BASE_RENDERING_CONTEXT_2D_CC).read_text(encoding="utf-8"))
        patch_image_data_buffer_cc((src / IMAGE_DATA_BUFFER_CC).read_text(encoding="utf-8"))
        patch_image_data_buffer_h((src / IMAGE_DATA_BUFFER_H).read_text(encoding="utf-8"))
        print(f"ready: {src / BASE_RENDERING_CONTEXT_2D_CC}")
        print(f"ready: {src / IMAGE_DATA_BUFFER_CC}")
        return
    for path in apply_patch(src):
        print(path.as_posix())


if __name__ == "__main__":
    main()
