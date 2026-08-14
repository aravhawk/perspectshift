#pragma once
#include "perceptshift/adapters/adapter.hpp"

#include <string>
#include <unordered_map>

namespace perceptshift::adapters {
struct YoloV8AdapterConfig {
  float confidence_threshold{0.25f};
  float iou_threshold{0.45f};
  int max_detections{100};
  int num_classes{80};
  float input_width{640.f};
  float input_height{640.f};
  std::string coordinate_space{"model_input_pixels"};
  std::string output_layout{"auto"};
  std::unordered_map<int, std::string> labels;
};
class YoloV8Adapter final : public Adapter {
public:
  explicit YoloV8Adapter(YoloV8AdapterConfig config) : config_(std::move(config)) {}
  [[nodiscard]] std::string name() const override { return "yolo_v8_detection"; }
  [[nodiscard]] bool provides_confidence_signal() const noexcept override { return true; }
  [[nodiscard]] Result<NormalizedOutput> postprocess(const TensorView& output) const override;
  [[nodiscard]] const YoloV8AdapterConfig& config() const noexcept { return config_; }

private:
  YoloV8AdapterConfig config_;
};
} // namespace perceptshift::adapters
