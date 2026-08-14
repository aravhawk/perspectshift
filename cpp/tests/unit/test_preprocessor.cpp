#include "perceptshift/image/preprocessor.hpp"

#include <gtest/gtest.h>
#include <algorithm>
#include <cmath>
#include <vector>

namespace {

// Independent trusted bilinear reference (pixel-center, replicate-edge).
void reference_bilinear_rgb(const std::vector<std::uint8_t>& src, std::size_t sw, std::size_t sh,
                            std::size_t dw, std::size_t dh, std::vector<float>& out_nchw) {
  out_nchw.assign(3 * dw * dh, 0.f);
  auto sample = [&](std::size_t x, std::size_t y, float& r, float& g, float& b) {
    const auto* p = src.data() + (y * sw + x) * 3;
    r = p[0];
    g = p[1];
    b = p[2];
  };
  for (std::size_t oy = 0; oy < dh; ++oy) {
    const float sy = (static_cast<float>(oy) + 0.5f) * static_cast<float>(sh) /
                         static_cast<float>(dh) -
                     0.5f;
    for (std::size_t ox = 0; ox < dw; ++ox) {
      const float sx = (static_cast<float>(ox) + 0.5f) * static_cast<float>(sw) /
                           static_cast<float>(dw) -
                       0.5f;
      const float max_x = static_cast<float>(sw - 1);
      const float max_y = static_cast<float>(sh - 1);
      const float csx = std::clamp(sx, 0.f, max_x);
      const float csy = std::clamp(sy, 0.f, max_y);
      const std::size_t x0 = static_cast<std::size_t>(std::floor(csx));
      const std::size_t y0 = static_cast<std::size_t>(std::floor(csy));
      const std::size_t x1 = std::min(x0 + 1, sw - 1);
      const std::size_t y1 = std::min(y0 + 1, sh - 1);
      const float fx = csx - static_cast<float>(x0);
      const float fy = csy - static_cast<float>(y0);
      float r00, g00, b00, r10, g10, b10, r01, g01, b01, r11, g11, b11;
      sample(x0, y0, r00, g00, b00);
      sample(x1, y0, r10, g10, b10);
      sample(x0, y1, r01, g01, b01);
      sample(x1, y1, r11, g11, b11);
      const float w00 = (1.f - fx) * (1.f - fy);
      const float w10 = fx * (1.f - fy);
      const float w01 = (1.f - fx) * fy;
      const float w11 = fx * fy;
      const float r = r00 * w00 + r10 * w10 + r01 * w01 + r11 * w11;
      const float g = g00 * w00 + g10 * w10 + g01 * w01 + g11 * w11;
      const float b = b00 * w00 + b10 * w10 + b01 * w01 + b11 * w11;
      const std::size_t plane = dw * dh;
      out_nchw[0 * plane + oy * dw + ox] = r;
      out_nchw[1 * plane + oy * dw + ox] = g;
      out_nchw[2 * plane + oy * dw + ox] = b;
    }
  }
}

} // namespace

TEST(PreprocessorTest, ScalarRgbNchw) {
  std::vector<std::uint8_t> pixels = {
      255, 0, 0, 0, 255, 0, 0, 0, 255, 255, 255, 255,
  };
  perceptshift::image::ImageView view;
  view.data = pixels.data();
  view.width = 2;
  view.height = 2;
  view.stride_bytes = 6;
  view.format = perceptshift::image::PixelFormat::Rgb8;

  perceptshift::image::PreprocessConfig cfg;
  cfg.width = 2;
  cfg.height = 2;
  cfg.layout = perceptshift::image::TensorLayout::Nchw;
  cfg.backend = perceptshift::image::PreprocessBackend::Scalar;
  cfg.scale = 1.f;
  cfg.mean = {0.f, 0.f, 0.f};
  cfg.std = {1.f, 1.f, 1.f};

  perceptshift::image::TensorBuffer buf;
  auto meta = perceptshift::image::preprocess_to_float_tensor(view, cfg, buf);
  ASSERT_TRUE(meta.ok());
  EXPECT_EQ(meta.value().impl, perceptshift::image::PreprocessImplUsed::Scalar);
  ASSERT_EQ(buf.size(), 12u);
  EXPECT_FLOAT_EQ(buf.data()[0], 255.f); // R plane first pixel
}

TEST(PreprocessorTest, BilinearMatchesIndependentReference) {
  // 2x2 source upscaled to 3x3 — hand-checkable intermediate pixels.
  std::vector<std::uint8_t> pixels = {
      0, 0, 0, 255, 0, 0, // row0: black, red
      0, 255, 0, 0, 0, 255, // row1: green, blue
  };
  std::vector<float> expected;
  reference_bilinear_rgb(pixels, 2, 2, 3, 3, expected);

  perceptshift::image::ImageView view;
  view.data = pixels.data();
  view.width = 2;
  view.height = 2;
  view.stride_bytes = 6;
  view.format = perceptshift::image::PixelFormat::Rgb8;

  perceptshift::image::PreprocessConfig cfg;
  cfg.width = 3;
  cfg.height = 3;
  cfg.layout = perceptshift::image::TensorLayout::Nchw;
  cfg.backend = perceptshift::image::PreprocessBackend::Scalar;
  cfg.scale = 1.f;
  cfg.mean = {0.f, 0.f, 0.f};
  cfg.std = {1.f, 1.f, 1.f};

  perceptshift::image::TensorBuffer buf;
  ASSERT_TRUE(perceptshift::image::preprocess_to_float_tensor(view, cfg, buf));
  ASSERT_EQ(buf.size(), expected.size());
  for (std::size_t i = 0; i < expected.size(); ++i) {
    EXPECT_NEAR(buf.data()[i], expected[i], 1e-4f) << "i=" << i;
  }
}

TEST(PreprocessorTest, OddDimensionsAndTinyImages) {
  // 1x1 → 2x2 must replicate the single pixel under bilinear+edge replicate.
  std::vector<std::uint8_t> pixels = {10, 20, 30};
  perceptshift::image::ImageView view;
  view.data = pixels.data();
  view.width = 1;
  view.height = 1;
  view.stride_bytes = 3;
  view.format = perceptshift::image::PixelFormat::Rgb8;

  perceptshift::image::PreprocessConfig cfg;
  cfg.width = 2;
  cfg.height = 2;
  cfg.backend = perceptshift::image::PreprocessBackend::Scalar;
  cfg.scale = 1.f;
  cfg.mean = {0.f, 0.f, 0.f};
  cfg.std = {1.f, 1.f, 1.f};

  perceptshift::image::TensorBuffer buf;
  ASSERT_TRUE(perceptshift::image::preprocess_to_float_tensor(view, cfg, buf));
  ASSERT_EQ(buf.size(), 12u);
  for (std::size_t i = 0; i < 4; ++i) {
    EXPECT_FLOAT_EQ(buf.data()[i], 10.f);
    EXPECT_FLOAT_EQ(buf.data()[4 + i], 20.f);
    EXPECT_FLOAT_EQ(buf.data()[8 + i], 30.f);
  }
}

TEST(PreprocessorTest, SourceColorHandlingPreserveBgr) {
  // BGR pixel: B=255, G=0, R=0. convert_to_rgb → R plane 0; preserve → first plane 255.
  std::vector<std::uint8_t> pixels = {255, 0, 0};
  perceptshift::image::ImageView view;
  view.data = pixels.data();
  view.width = 1;
  view.height = 1;
  view.stride_bytes = 3;
  view.format = perceptshift::image::PixelFormat::Bgr8;

  perceptshift::image::PreprocessConfig cfg;
  cfg.width = 1;
  cfg.height = 1;
  cfg.backend = perceptshift::image::PreprocessBackend::Scalar;
  cfg.scale = 1.f;
  cfg.mean = {0.f, 0.f, 0.f};
  cfg.std = {1.f, 1.f, 1.f};
  cfg.source_color_handling = perceptshift::image::SourceColorHandling::ConvertToRgb;

  perceptshift::image::TensorBuffer converted;
  ASSERT_TRUE(perceptshift::image::preprocess_to_float_tensor(view, cfg, converted));
  EXPECT_FLOAT_EQ(converted.data()[0], 0.f);   // R
  EXPECT_FLOAT_EQ(converted.data()[1], 0.f);   // G
  EXPECT_FLOAT_EQ(converted.data()[2], 255.f); // B

  cfg.source_color_handling = perceptshift::image::SourceColorHandling::Preserve;
  perceptshift::image::TensorBuffer preserved;
  ASSERT_TRUE(perceptshift::image::preprocess_to_float_tensor(view, cfg, preserved));
  EXPECT_FLOAT_EQ(preserved.data()[0], 255.f); // B preserved as channel0
  EXPECT_FLOAT_EQ(preserved.data()[1], 0.f);
  EXPECT_FLOAT_EQ(preserved.data()[2], 0.f);
}

TEST(PreprocessorTest, RejectsUnsupportedFormat) {
  std::vector<std::uint8_t> pixels = {1, 2, 3};
  perceptshift::image::ImageView view;
  view.data = pixels.data();
  view.width = 1;
  view.height = 1;
  view.stride_bytes = 3;
  view.format = perceptshift::image::PixelFormat::Bgr8;

  perceptshift::image::PreprocessConfig cfg;
  cfg.width = 1;
  cfg.height = 1;
  cfg.backend = perceptshift::image::PreprocessBackend::Scalar;
  cfg.accepted_source_formats = {perceptshift::image::PixelFormat::Rgb8};
  perceptshift::image::TensorBuffer buf;
  auto meta = perceptshift::image::preprocess_to_float_tensor(view, cfg, buf);
  EXPECT_FALSE(meta.ok());
}

TEST(PreprocessorTest, Uint8ToFloatNormalization) {
  std::vector<std::uint8_t> pixels = {255, 128, 0};
  perceptshift::image::ImageView view;
  view.data = pixels.data();
  view.width = 1;
  view.height = 1;
  view.stride_bytes = 3;
  view.format = perceptshift::image::PixelFormat::Rgb8;

  perceptshift::image::PreprocessConfig cfg;
  cfg.width = 1;
  cfg.height = 1;
  cfg.backend = perceptshift::image::PreprocessBackend::Scalar;
  cfg.scale = 1.f / 255.f;
  cfg.mean = {0.f, 0.f, 0.f};
  cfg.std = {1.f, 1.f, 1.f};
  perceptshift::image::TensorBuffer buf;
  ASSERT_TRUE(perceptshift::image::preprocess_to_float_tensor(view, cfg, buf));
  EXPECT_NEAR(buf.data()[0], 1.f, 1e-5);
  EXPECT_NEAR(buf.data()[1], 128.f / 255.f, 1e-5);
  EXPECT_NEAR(buf.data()[2], 0.f, 1e-5);
}

#if defined(__aarch64__) || defined(__ARM_NEON)
TEST(PreprocessorTest, NeonMatchesScalar) {
  std::vector<std::uint8_t> pixels(64 * 64 * 3);
  for (std::size_t i = 0; i < pixels.size(); ++i) {
    pixels[i] = static_cast<std::uint8_t>(i % 251);
  }
  perceptshift::image::ImageView view;
  view.data = pixels.data();
  view.width = 64;
  view.height = 64;
  view.stride_bytes = 64 * 3;
  view.format = perceptshift::image::PixelFormat::Rgb8;

  perceptshift::image::PreprocessConfig cfg;
  cfg.width = 32;
  cfg.height = 32;
  cfg.layout = perceptshift::image::TensorLayout::Nchw;
  cfg.mean = {0.f, 0.f, 0.f};
  cfg.std = {1.f, 1.f, 1.f};

  perceptshift::image::TensorBuffer a, b;
  cfg.backend = perceptshift::image::PreprocessBackend::Scalar;
  ASSERT_TRUE(perceptshift::image::preprocess_to_float_tensor(view, cfg, a));
  cfg.backend = perceptshift::image::PreprocessBackend::NeonAuto;
  ASSERT_TRUE(perceptshift::image::preprocess_to_float_tensor(view, cfg, b));
  ASSERT_EQ(a.size(), b.size());
  for (std::size_t i = 0; i < a.size(); ++i) {
    EXPECT_NEAR(a.data()[i], b.data()[i], 1e-4);
  }
}

TEST(PreprocessorTest, NeonMatchesScalarPropertyRandom) {
  for (int trial = 0; trial < 8; ++trial) {
    const std::size_t sw = 7 + static_cast<std::size_t>(trial * 3);
    const std::size_t sh = 5 + static_cast<std::size_t>(trial * 2);
    const std::size_t dw = 4 + static_cast<std::size_t>(trial);
    const std::size_t dh = 3 + static_cast<std::size_t>(trial % 3);
    std::vector<std::uint8_t> pixels(sw * sh * 3);
    for (std::size_t i = 0; i < pixels.size(); ++i) {
      pixels[i] = static_cast<std::uint8_t>((i * 37U + static_cast<std::size_t>(trial) * 11U) % 255U);
    }
    perceptshift::image::ImageView view;
    view.data = pixels.data();
    view.width = sw;
    view.height = sh;
    view.stride_bytes = sw * 3;
    view.format = perceptshift::image::PixelFormat::Rgb8;
    perceptshift::image::PreprocessConfig cfg;
    cfg.width = dw;
    cfg.height = dh;
    cfg.scale = 1.f / 255.f;
    cfg.mean = {0.1f, 0.2f, 0.3f};
    cfg.std = {0.5f, 0.5f, 0.5f};
    perceptshift::image::TensorBuffer a, b;
    cfg.backend = perceptshift::image::PreprocessBackend::Scalar;
    ASSERT_TRUE(perceptshift::image::preprocess_to_float_tensor(view, cfg, a));
    cfg.backend = perceptshift::image::PreprocessBackend::NeonForced;
    ASSERT_TRUE(perceptshift::image::preprocess_to_float_tensor(view, cfg, b));
    ASSERT_EQ(a.size(), b.size());
    for (std::size_t i = 0; i < a.size(); ++i) {
      EXPECT_NEAR(a.data()[i], b.data()[i], 1e-4f);
    }
  }
}
#endif
