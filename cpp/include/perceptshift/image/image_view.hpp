#pragma once
#include "perceptshift/image/pixel_format.hpp"
#include "perceptshift/result.hpp"

#include <cstddef>
#include <cstdint>
namespace perceptshift::image {
struct ImageView {
  const std::uint8_t* data{nullptr};
  std::size_t width{0};
  std::size_t height{0};
  std::size_t stride_bytes{0};
  PixelFormat format{PixelFormat::Rgb8};
  [[nodiscard]] bool valid() const noexcept {
    return data != nullptr && width > 0 && height > 0 &&
           stride_bytes >= width * static_cast<std::size_t>(channel_count(format));
  }
};
[[nodiscard]] Result<void> validate_image_view(const ImageView& image);
} // namespace perceptshift::image
