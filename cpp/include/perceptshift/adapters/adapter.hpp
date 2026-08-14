#pragma once

#include "perceptshift/result.hpp"

#include <cstdint>
#include <string>
#include <vector>

namespace perceptshift::adapters {

struct TensorView {
  const float* data{nullptr};
  std::vector<std::int64_t> shape;
};

struct Classification {
  int class_id{0};
  float score{0.f};
  std::string label;
};

// Canonical detection box: top-left (x, y) plus width/height in model-input pixels.
// YOLO center-format outputs are converted in YoloV8Adapter before emission.
struct Detection {
  int class_id{0};
  float score{0.f};
  float x{0.f};
  float y{0.f};
  float w{0.f};
  float h{0.f};
  std::string label;
};

struct NormalizedOutput {
  std::string task;
  std::vector<Classification> classifications;
  std::vector<Detection> detections;
  std::vector<float> raw_values;
  float confidence_signal{-1.f};
};

class Adapter {
public:
  virtual ~Adapter() = default;
  [[nodiscard]] virtual std::string name() const = 0;
  [[nodiscard]] virtual bool provides_confidence_signal() const noexcept { return false; }
  [[nodiscard]] virtual Result<NormalizedOutput> postprocess(const TensorView& output) const = 0;
};

} // namespace perceptshift::adapters
