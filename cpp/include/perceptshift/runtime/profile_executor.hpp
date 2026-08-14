#pragma once

#include "perceptshift/adapters/adapter.hpp"
#include "perceptshift/image/preprocess_config.hpp"
#include "perceptshift/image/preprocessor.hpp"
#include "perceptshift/image/tensor_buffer.hpp"
#include "perceptshift/inference/inference_request.hpp"
#include "perceptshift/inference/onnx_session.hpp"
#include "perceptshift/result.hpp"

#include <cstdint>
#include <memory>
#include <nlohmann/json.hpp>
#include <string>
#include <vector>

namespace perceptshift::runtime {

struct ProfileExecutorInput {
  enum class Kind { TensorBytes, RawImageBytes, ZerosSmoke };
  Kind kind{Kind::TensorBytes};
  std::vector<std::uint8_t> payload;
  std::size_t width{0};
  std::size_t height{0};
  std::size_t stride_bytes{0};
  std::string pixel_format{"rgb8"};
  std::int64_t sequence_id{0};
  std::string sample_id;
  std::string trace_id;
  std::int64_t source_timestamp_ns{0};
  std::int64_t receive_steady_ns{0};
  bool allow_zeros_smoke{false};
};

struct ProfileExecutorResult {
  bool ok{false};
  adapters::NormalizedOutput output;
  double preprocess_ms{0.0};
  double inference_ms{0.0};
  double postprocess_ms{0.0};
  double executor_ms{0.0};
  std::string active_provider_summary;
  std::string preprocess_impl{"scalar"};
  image::PreprocessTransform transform{};
  nlohmann::json tensor_contract = nlohmann::json::object();
  Error error{};
};

/// Shared production execution pipeline used by RuntimeEngine and bench-worker.
class ProfileExecutor {
public:
  ProfileExecutor(inference::OnnxSession* session, adapters::Adapter* adapter,
                  image::PreprocessConfig preprocess);

  [[nodiscard]] Result<ProfileExecutorResult> execute(const ProfileExecutorInput& input) const;
  [[nodiscard]] const image::PreprocessConfig& preprocess() const noexcept { return preprocess_; }

private:
  inference::OnnxSession* session_;
  adapters::Adapter* adapter_;
  image::PreprocessConfig preprocess_;
};

} // namespace perceptshift::runtime
