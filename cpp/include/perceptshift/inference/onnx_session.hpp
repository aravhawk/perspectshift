#pragma once

#include "perceptshift/inference/execution_provider_report.hpp"
#include "perceptshift/inference/inference_request.hpp"
#include "perceptshift/inference/inference_result.hpp"
#include "perceptshift/inference/model_metadata.hpp"
#include "perceptshift/result.hpp"

#include <memory>
#include <string>
#include <vector>

namespace perceptshift::inference {

struct SessionOptions {
  std::vector<std::string> provider_order{"CPUExecutionProvider"};
  int intra_op_threads{1};
  int inter_op_threads{1};
  bool allow_intra_op_spinning{false};
  std::string graph_optimization_level{"all"};
  int xnnpack_intra_op_threads{1};
};

class OnnxSession {
public:
  virtual ~OnnxSession() = default;
  [[nodiscard]] virtual const ModelMetadata& metadata() const = 0;
  [[nodiscard]] virtual Result<InferenceResult> run(const InferenceRequest& request) = 0;
  [[nodiscard]] virtual Result<void> warmup(int iterations) = 0;
  [[nodiscard]] virtual ExecutionProviderReport provider_report() const = 0;
};

[[nodiscard]] bool onnxruntime_available() noexcept;

} // namespace perceptshift::inference
