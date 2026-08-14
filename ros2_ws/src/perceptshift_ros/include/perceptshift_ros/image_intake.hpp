// Copyright 2026 PerceptShift Authors
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <cstdint>
#include <optional>
#include <sensor_msgs/msg/image.hpp>
#include <string>

namespace perceptshift_ros {

struct ValidatedImageView {
  uint32_t width{0};
  uint32_t height{0};
  uint32_t step{0};
  std::string encoding;
  std::size_t expected_bytes{0};
  bool copied{false};
};

struct ImageValidationResult {
  bool ok{false};
  std::string reason_code;
  std::optional<ValidatedImageView> view;
};

/**
 * Validates sensor_msgs/Image against encodings supported by the core pixel formats.
 * Does not perform preprocessing; that remains in libperceptshift_core.
 */
class ImageIntake {
public:
  ImageValidationResult validate(const sensor_msgs::msg::Image& image) const;

  void set_capacity(int capacity) { capacity_ = capacity > 0 ? capacity : 1; }
  int capacity() const { return capacity_; }

  bool offer(const sensor_msgs::msg::Image::ConstSharedPtr& image);
  sensor_msgs::msg::Image::ConstSharedPtr take_latest();
  std::size_t depth() const { return depth_; }
  uint64_t dropped() const { return dropped_; }

private:
  int capacity_{1};
  std::size_t depth_{0};
  uint64_t dropped_{0};
  sensor_msgs::msg::Image::ConstSharedPtr latest_;
};

} // namespace perceptshift_ros
