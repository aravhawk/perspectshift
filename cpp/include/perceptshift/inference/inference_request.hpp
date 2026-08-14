#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace perceptshift::inference {

struct NamedTensorView {
  std::string name;
  std::vector<std::int64_t> shape;
  std::string element_type;
  const void* data{nullptr};
  std::size_t byte_size{0};
};

struct InferenceRequest {
  std::vector<NamedTensorView> inputs;
  std::int64_t sequence_id{0};
  std::string trace_id;
  std::int64_t source_timestamp_ns{0};
  std::int64_t receive_steady_ns{0};
};

} // namespace perceptshift::inference
