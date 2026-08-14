#pragma once
#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

#include "perceptshift/error.hpp"
#include "perceptshift/image/pixel_format.hpp"
#include "perceptshift/image/preprocess_config.hpp"
#include "perceptshift/result.hpp"

namespace perceptshift::image {

/**
 * Validate tightly packed (or explicitly strided) raw image bytes.
 *
 * v1 contract: payload size must equal stride_bytes * height exactly.
 * Encoded PNG/JPEG/WebP bytes labeled as rgb8 are rejected because their
 * compressed size will not match the declared geometry.
 */
[[nodiscard]] inline Result<void>
validate_raw_image_payload(const std::uint8_t* /*data*/, std::size_t payload_size,
                           std::size_t width, std::size_t height, std::size_t stride_bytes,
                           PixelFormat fmt, const PreprocessConfig& cfg) {
  const bool accepted =
      std::find(cfg.accepted_source_formats.begin(), cfg.accepted_source_formats.end(), fmt) !=
      cfg.accepted_source_formats.end();
  if (!accepted) {
    return Error::make(ErrorCode::InputUnsupported,
                       std::string("pixel format not accepted by preprocess contract: ") +
                           to_string(fmt));
  }
  if (width == 0 || height == 0) {
    return Error::make(ErrorCode::InputUnsupported, "image requires positive width/height");
  }
  const int channels = channel_count(fmt);
  const std::size_t min_stride = width * static_cast<std::size_t>(channels);
  const std::size_t stride = stride_bytes > 0 ? stride_bytes : min_stride;
  if (stride < min_stride) {
    return Error::make(ErrorCode::InputUnsupported, "image stride shorter than minimum for format");
  }
  const std::size_t needed = stride * height;
  if (payload_size != needed) {
    return Error::make(ErrorCode::DatasetInvalid,
                       "image payload size " + std::to_string(payload_size) +
                           " != stride*height " + std::to_string(needed) +
                           " for declared format (encoded PNG/JPEG bytes are not raw rgb8)");
  }
  return Result<void>::success();
}

} // namespace perceptshift::image
