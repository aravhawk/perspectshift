#pragma once
#include <array>
#include <cstddef>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

#include "perceptshift/error.hpp"
#include "perceptshift/image/pixel_format.hpp"
#include "perceptshift/result.hpp"

namespace perceptshift::image {

enum class TensorLayout { Nchw, Nhwc };
enum class PreprocessBackend { Scalar, NeonAuto, NeonForced };
enum class ResizeMode { Stretch };
enum class ResizeInterpolation { Bilinear };
enum class SourceColorHandling { Preserve, ConvertToRgb };

struct PreprocessConfig {
  std::size_t width{0};
  std::size_t height{0};
  TensorLayout layout{TensorLayout::Nchw};
  PreprocessBackend backend{PreprocessBackend::NeonAuto};
  float scale{1.0f / 255.0f};
  std::array<float, 3> mean{0.f, 0.f, 0.f};
  std::array<float, 3> std{1.f, 1.f, 1.f};
  bool swap_rb{false};
  ResizeMode resize_mode{ResizeMode::Stretch};
  ResizeInterpolation resize_interpolation{ResizeInterpolation::Bilinear};
  SourceColorHandling source_color_handling{SourceColorHandling::ConvertToRgb};
  std::vector<PixelFormat> accepted_source_formats{
      PixelFormat::Rgb8, PixelFormat::Bgr8, PixelFormat::Rgba8, PixelFormat::Bgra8,
      PixelFormat::Mono8};
  std::string output_dtype{"float32"};

  // Compatibility aliases used by older manifests.
  [[nodiscard]] std::size_t input_width() const noexcept { return width; }
  [[nodiscard]] std::size_t input_height() const noexcept { return height; }
};

struct PreprocessTransform {
  ResizeMode resize_mode{ResizeMode::Stretch};
  float scale_x{1.f};
  float scale_y{1.f};
  float pad_x{0.f};
  float pad_y{0.f};
  std::size_t source_width{0};
  std::size_t source_height{0};
  std::size_t model_width{0};
  std::size_t model_height{0};
};

[[nodiscard]] Result<PreprocessConfig> preprocess_config_from_json(const nlohmann::json& doc);
[[nodiscard]] nlohmann::json preprocess_config_to_json(const PreprocessConfig& cfg);
[[nodiscard]] PreprocessTransform make_stretch_transform(std::size_t source_w, std::size_t source_h,
                                                         std::size_t model_w, std::size_t model_h);

} // namespace perceptshift::image
