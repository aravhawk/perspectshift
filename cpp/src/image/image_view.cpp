#include "perceptshift/image/image_view.hpp"

#include "perceptshift/result.hpp"
#include "perceptshift/util/checked_math.hpp"

namespace perceptshift::image {

Result<void> validate_image_view(const ImageView& image) {
  if (image.data == nullptr) {
    return Err(ErrorCode::InputUnsupported, "image data pointer is null");
  }
  if (image.width == 0 || image.height == 0) {
    return Err(ErrorCode::InputUnsupported, "image dimensions must be positive");
  }
  const auto channels = static_cast<std::size_t>(channel_count(image.format));
  auto min_stride = util::checked_mul_size(image.width, channels);
  if (!min_stride) {
    return Err(ErrorCode::InputUnsupported, "image stride overflow");
  }
  if (image.stride_bytes < min_stride.value()) {
    return Err(ErrorCode::InputUnsupported, "image stride is too small for width/format");
  }
  auto total = util::checked_mul_size(image.height, image.stride_bytes);
  if (!total) {
    return Err(ErrorCode::InputUnsupported, "image size overflow");
  }
  return Ok();
}

} // namespace perceptshift::image
