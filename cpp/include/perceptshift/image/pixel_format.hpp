#pragma once
#include <cstdint>
#include <string_view>
namespace perceptshift::image {
enum class PixelFormat { Rgb8, Bgr8, Rgba8, Bgra8, Mono8 };
[[nodiscard]] inline int channel_count(PixelFormat fmt) noexcept {
  switch (fmt) {
  case PixelFormat::Mono8:
    return 1;
  case PixelFormat::Rgb8:
  case PixelFormat::Bgr8:
    return 3;
  case PixelFormat::Rgba8:
  case PixelFormat::Bgra8:
    return 4;
  }
  return 0;
}
[[nodiscard]] inline const char* to_string(PixelFormat fmt) noexcept {
  switch (fmt) {
  case PixelFormat::Rgb8:
    return "rgb8";
  case PixelFormat::Bgr8:
    return "bgr8";
  case PixelFormat::Rgba8:
    return "rgba8";
  case PixelFormat::Bgra8:
    return "bgra8";
  case PixelFormat::Mono8:
    return "mono8";
  }
  return "unknown";
}
[[nodiscard]] inline bool parse_pixel_format(std::string_view s, PixelFormat& out) noexcept {
  if (s == "rgb8") {
    out = PixelFormat::Rgb8;
    return true;
  }
  if (s == "bgr8") {
    out = PixelFormat::Bgr8;
    return true;
  }
  if (s == "rgba8") {
    out = PixelFormat::Rgba8;
    return true;
  }
  if (s == "bgra8") {
    out = PixelFormat::Bgra8;
    return true;
  }
  if (s == "mono8") {
    out = PixelFormat::Mono8;
    return true;
  }
  return false;
}
} // namespace perceptshift::image
