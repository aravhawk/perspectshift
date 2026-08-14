#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace perceptshift::inference {

struct NamedTensor {
  std::string name;
  std::vector<std::int64_t> shape;
  std::string element_type;
  std::vector<std::uint8_t> data;
};

struct InferenceResult {
  std::vector<NamedTensor> outputs;
  std::int64_t inference_start_steady_ns{0};
  std::int64_t inference_end_steady_ns{0};
  std::string active_provider_summary;
};

} // namespace perceptshift::inference
