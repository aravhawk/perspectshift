#pragma once

#include "perceptshift/inference/onnx_session.hpp"
#include "perceptshift/inference/tensor_spec.hpp"
#include "perceptshift/result.hpp"
#include "perceptshift/util/file_security.hpp"

#include <filesystem>
#include <memory>
#include <optional>
#include <string>
#include <vector>

namespace perceptshift::inference {

struct SessionCreateRequest {
  std::filesystem::path model_path;
  std::optional<std::string> expected_sha256;
  SessionOptions options;
  std::vector<TensorSpec> expected_inputs;
  std::vector<TensorSpec> expected_outputs;
  util::FileSecurityPolicy security;
};

[[nodiscard]] Result<std::unique_ptr<OnnxSession>>
create_onnx_session(const SessionCreateRequest& request);

} // namespace perceptshift::inference
