// Copyright 2026 PerceptShift Authors
// SPDX-License-Identifier: Apache-2.0

#include "perceptshift_ros/image_intake.hpp"

#include <cstring>

namespace perceptshift_ros {
namespace {

bool encoding_supported(const std::string& encoding) {
  return encoding == "rgb8" || encoding == "bgr8" || encoding == "mono8" || encoding == "rgba8" ||
         encoding == "bgra8";
}

std::size_t bytes_per_pixel(const std::string& encoding) {
  if (encoding == "mono8") {
    return 1;
  }
  if (encoding == "rgb8" || encoding == "bgr8") {
    return 3;
  }
  if (encoding == "rgba8" || encoding == "bgra8") {
    return 4;
  }
  return 0;
}

} // namespace

ImageValidationResult ImageIntake::validate(const sensor_msgs::msg::Image& image) const {
  ImageValidationResult result;
  if (image.width == 0 || image.height == 0) {
    result.reason_code = "invalid_dimensions";
    return result;
  }
  if (!encoding_supported(image.encoding)) {
    result.reason_code = "unsupported_encoding";
    return result;
  }
  const auto bpp = bytes_per_pixel(image.encoding);
  if (bpp == 0) {
    result.reason_code = "unsupported_encoding";
    return result;
  }
  const std::size_t min_step = static_cast<std::size_t>(image.width) * bpp;
  if (image.step < min_step) {
    result.reason_code = "invalid_step";
    return result;
  }
  const std::size_t expected = static_cast<std::size_t>(image.step) * image.height;
  if (image.data.size() < expected) {
    result.reason_code = "invalid_data_length";
    return result;
  }

  ValidatedImageView view;
  view.width = image.width;
  view.height = image.height;
  view.step = image.step;
  view.encoding = image.encoding;
  view.expected_bytes = expected;
  view.copied = false;
  result.ok = true;
  result.view = view;
  return result;
}

bool ImageIntake::offer(const sensor_msgs::msg::Image::ConstSharedPtr& image) {
  if (!image) {
    return false;
  }
  if (capacity_ <= 1) {
    if (latest_) {
      ++dropped_;
    }
    latest_ = image;
    depth_ = 1;
    return true;
  }
  // Bounded latest-only policy for capacity > 1 still retains only the newest frame
  // to keep ROS memory bounded under high-rate input.
  if (latest_) {
    ++dropped_;
  }
  latest_ = image;
  depth_ = 1;
  return true;
}

sensor_msgs::msg::Image::ConstSharedPtr ImageIntake::take_latest() {
  auto out = latest_;
  latest_.reset();
  depth_ = 0;
  return out;
}

} // namespace perceptshift_ros
