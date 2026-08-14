#include "perceptshift/image/raw_image_validation.hpp"

#include <cstdint>
#include <string>
#include <vector>

#include <gtest/gtest.h>

TEST(RawImageValidation, AcceptsExactPackedRgb8) {
  const std::size_t width = 8;
  const std::size_t height = 8;
  const std::size_t stride = width * 3;
  std::vector<std::uint8_t> raw(stride * height, 42);
  perceptshift::image::PreprocessConfig cfg;
  cfg.width = 8;
  cfg.height = 8;
  auto ok = perceptshift::image::validate_raw_image_payload(
      raw.data(), raw.size(), width, height, stride, perceptshift::image::PixelFormat::Rgb8, cfg);
  ASSERT_TRUE(ok.ok()) << ok.error().message;
}

TEST(RawImageValidation, RejectsPngBytesLabeledAsRgb8) {
  // Encoded PNG magic is not a tightly packed 8x8 rgb8 frame (192 bytes).
  const std::vector<std::uint8_t> png = {0x89, 'P', 'N', 'G', 0x0D, 0x0A, 0x1A, 0x0A,
                                         0x00, 0x00, 0x00, 0x0D, 'I', 'H', 'D', 'R'};
  perceptshift::image::PreprocessConfig cfg;
  cfg.width = 8;
  cfg.height = 8;
  auto bad = perceptshift::image::validate_raw_image_payload(
      png.data(), png.size(), 8, 8, 24, perceptshift::image::PixelFormat::Rgb8, cfg);
  ASSERT_FALSE(bad.ok());
  EXPECT_EQ(bad.error().code, perceptshift::ErrorCode::DatasetInvalid);
  EXPECT_NE(bad.error().message.find("stride*height"), std::string::npos);
  EXPECT_NE(bad.error().message.find("PNG/JPEG"), std::string::npos);
}

TEST(RawImageValidation, RejectsTrailingPaddingBeyondStrideHeight) {
  const std::size_t width = 4;
  const std::size_t height = 4;
  const std::size_t stride = width * 3;
  std::vector<std::uint8_t> raw(stride * height + 16, 1);
  perceptshift::image::PreprocessConfig cfg;
  auto bad = perceptshift::image::validate_raw_image_payload(
      raw.data(), raw.size(), width, height, stride, perceptshift::image::PixelFormat::Rgb8, cfg);
  ASSERT_FALSE(bad.ok());
}
