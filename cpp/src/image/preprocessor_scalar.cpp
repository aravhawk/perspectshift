#include "perceptshift/image/preprocessor.hpp"
#include "perceptshift/util/checked_math.hpp"

#include <algorithm>
#include <cmath>

namespace perceptshift::image {
namespace {

// Pixel-center mapping: destination pixel (ox, oy) maps to source coordinate
//   sx = (ox + 0.5) * src_w / dst_w - 0.5
// Border: clamp sample indices to [0, dim-1] (replicate edge).
// Rounding/casting: bilinear weights stay float; final tensor values remain float32.

[[nodiscard]] bool format_accepted(const PreprocessConfig& config, PixelFormat fmt) {
  return std::find(config.accepted_source_formats.begin(), config.accepted_source_formats.end(),
                    fmt) != config.accepted_source_formats.end();
}

inline void sample_channels(const ImageView& image, std::size_t x, std::size_t y,
                            SourceColorHandling color_handling, float& c0, float& c1, float& c2) {
  const auto* row = image.data + y * image.stride_bytes;
  switch (image.format) {
  case PixelFormat::Rgb8: {
    const auto* p = row + x * 3;
    c0 = p[0];
    c1 = p[1];
    c2 = p[2];
    break;
  }
  case PixelFormat::Bgr8: {
    const auto* p = row + x * 3;
    if (color_handling == SourceColorHandling::Preserve) {
      c0 = p[0];
      c1 = p[1];
      c2 = p[2];
    } else {
      c0 = p[2];
      c1 = p[1];
      c2 = p[0];
    }
    break;
  }
  case PixelFormat::Rgba8: {
    const auto* p = row + x * 4;
    c0 = p[0];
    c1 = p[1];
    c2 = p[2];
    break;
  }
  case PixelFormat::Bgra8: {
    const auto* p = row + x * 4;
    if (color_handling == SourceColorHandling::Preserve) {
      c0 = p[0];
      c1 = p[1];
      c2 = p[2];
    } else {
      c0 = p[2];
      c1 = p[1];
      c2 = p[0];
    }
    break;
  }
  case PixelFormat::Mono8: {
    const float v = row[x];
    c0 = c1 = c2 = v;
    break;
  }
  }
}

inline void bilinear_sample(const ImageView& image, float sx, float sy,
                            SourceColorHandling color_handling, float& c0, float& c1, float& c2) {
  if (image.width == 0 || image.height == 0) {
    c0 = c1 = c2 = 0.f;
    return;
  }
  const float max_x = static_cast<float>(image.width - 1);
  const float max_y = static_cast<float>(image.height - 1);
  const float clamped_sx = std::clamp(sx, 0.f, max_x);
  const float clamped_sy = std::clamp(sy, 0.f, max_y);
  const std::size_t x0 = static_cast<std::size_t>(std::floor(clamped_sx));
  const std::size_t y0 = static_cast<std::size_t>(std::floor(clamped_sy));
  const std::size_t x1 = std::min(x0 + 1, image.width - 1);
  const std::size_t y1 = std::min(y0 + 1, image.height - 1);
  const float fx = clamped_sx - static_cast<float>(x0);
  const float fy = clamped_sy - static_cast<float>(y0);
  const float w00 = (1.f - fx) * (1.f - fy);
  const float w10 = fx * (1.f - fy);
  const float w01 = (1.f - fx) * fy;
  const float w11 = fx * fy;

  float a0 = 0, a1 = 0, a2 = 0;
  float b0 = 0, b1 = 0, b2 = 0;
  float c0v = 0, c1v = 0, c2v = 0;
  float d0 = 0, d1 = 0, d2 = 0;
  sample_channels(image, x0, y0, color_handling, a0, a1, a2);
  sample_channels(image, x1, y0, color_handling, b0, b1, b2);
  sample_channels(image, x0, y1, color_handling, c0v, c1v, c2v);
  sample_channels(image, x1, y1, color_handling, d0, d1, d2);
  c0 = a0 * w00 + b0 * w10 + c0v * w01 + d0 * w11;
  c1 = a1 * w00 + b1 * w10 + c1v * w01 + d1 * w11;
  c2 = a2 * w00 + b2 * w10 + c2v * w01 + d2 * w11;
}

} // namespace

Result<PreprocessResultMeta>
preprocess_scalar(const ImageView& image, const PreprocessConfig& config, TensorBuffer& output) {
  if (!image.valid())
    return Error::make(ErrorCode::InputUnsupported, "invalid image view");
  if (config.width == 0 || config.height == 0)
    return Error::make(ErrorCode::ConfigInvalid, "preprocess width/height must be positive");
  if (config.std[0] == 0.f || config.std[1] == 0.f || config.std[2] == 0.f)
    return Error::make(ErrorCode::ConfigInvalid, "preprocess std cannot be zero");
  if (!format_accepted(config, image.format)) {
    return Error::make(ErrorCode::InputUnsupported,
                       "source pixel format rejected by accepted_source_formats");
  }
  if (config.resize_interpolation != ResizeInterpolation::Bilinear) {
    return Error::make(ErrorCode::ConfigInvalid,
                       "unsupported resize_interpolation (v1 requires bilinear)");
  }

  const std::size_t plane = config.width * config.height;
  auto total = util::checked_mul_size(plane, 3);
  if (!total)
    return total.error();
  output.resize_floats(total.value());
  float* out = output.data();
  for (std::size_t oy = 0; oy < config.height; ++oy) {
    const float sy = (static_cast<float>(oy) + 0.5f) * static_cast<float>(image.height) /
                         static_cast<float>(config.height) -
                     0.5f;
    for (std::size_t ox = 0; ox < config.width; ++ox) {
      const float sx = (static_cast<float>(ox) + 0.5f) * static_cast<float>(image.width) /
                           static_cast<float>(config.width) -
                       0.5f;
      float r = 0, g = 0, b = 0;
      bilinear_sample(image, sx, sy, config.source_color_handling, r, g, b);
      if (config.swap_rb)
        std::swap(r, b);
      r = (r * config.scale - config.mean[0]) / config.std[0];
      g = (g * config.scale - config.mean[1]) / config.std[1];
      b = (b * config.scale - config.mean[2]) / config.std[2];
      if (config.layout == TensorLayout::Nchw) {
        out[0 * plane + oy * config.width + ox] = r;
        out[1 * plane + oy * config.width + ox] = g;
        out[2 * plane + oy * config.width + ox] = b;
      } else {
        const std::size_t idx = (oy * config.width + ox) * 3;
        out[idx + 0] = r;
        out[idx + 1] = g;
        out[idx + 2] = b;
      }
    }
  }
  PreprocessResultMeta meta;
  meta.impl = PreprocessImplUsed::Scalar;
  return meta;
}
} // namespace perceptshift::image
