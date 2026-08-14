#pragma once

#include "perceptshift/inference/tensor_spec.hpp"

#include <string>
#include <vector>

namespace perceptshift::inference {

struct ModelMetadata {
  std::string model_path;
  std::string model_sha256;
  std::vector<TensorSpec> inputs;
  std::vector<TensorSpec> outputs;
  std::string onnxruntime_version;
  std::vector<std::string> available_providers;
};

} // namespace perceptshift::inference
