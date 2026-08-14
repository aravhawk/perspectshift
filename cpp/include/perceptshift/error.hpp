#pragma once

#include <string>
#include <utility>
#include <vector>

namespace perceptshift {

enum class ErrorCode {
  ConfigInvalid,
  SchemaUnsupported,
  PathUnsafe,
  FileIntegrityFailed,
  SignatureRequired,
  SignatureInvalid,
  ModelInvalid,
  ModelResourceLimit,
  ModelTensorMismatch,
  ModelProviderUnavailable,
  ModelProviderFallbackExcessive,
  DatasetInvalid,
  DatasetLeakage,
  QuantizationFailed,
  QualityGateFailed,
  EquivalenceGateFailed,
  BenchmarkEnvironmentInvalid,
  BenchmarkWorkerCrashed,
  BenchmarkTimeout,
  ProfileIncompatible,
  ProfileWarmupFailed,
  NoEligibleProfile,
  InputStale,
  InputUnsupported,
  InferenceFailed,
  PostprocessFailed,
  ResourceExhausted,
  TelemetryUnavailable,
  RosLifecycleError,
  AuthRequired,
  AuthInvalid,
  DatabaseError,
  InternalInvariantFailed,
};

[[nodiscard]] inline const char* to_string(ErrorCode code) noexcept {
  switch (code) {
  case ErrorCode::ConfigInvalid:
    return "CONFIG_INVALID";
  case ErrorCode::SchemaUnsupported:
    return "SCHEMA_UNSUPPORTED";
  case ErrorCode::PathUnsafe:
    return "PATH_UNSAFE";
  case ErrorCode::FileIntegrityFailed:
    return "FILE_INTEGRITY_FAILED";
  case ErrorCode::SignatureRequired:
    return "SIGNATURE_REQUIRED";
  case ErrorCode::SignatureInvalid:
    return "SIGNATURE_INVALID";
  case ErrorCode::ModelInvalid:
    return "MODEL_INVALID";
  case ErrorCode::ModelResourceLimit:
    return "MODEL_RESOURCE_LIMIT";
  case ErrorCode::ModelTensorMismatch:
    return "MODEL_TENSOR_MISMATCH";
  case ErrorCode::ModelProviderUnavailable:
    return "MODEL_PROVIDER_UNAVAILABLE";
  case ErrorCode::ModelProviderFallbackExcessive:
    return "MODEL_PROVIDER_FALLBACK_EXCESSIVE";
  case ErrorCode::DatasetInvalid:
    return "DATASET_INVALID";
  case ErrorCode::DatasetLeakage:
    return "DATASET_LEAKAGE";
  case ErrorCode::QuantizationFailed:
    return "QUANTIZATION_FAILED";
  case ErrorCode::QualityGateFailed:
    return "QUALITY_GATE_FAILED";
  case ErrorCode::EquivalenceGateFailed:
    return "EQUIVALENCE_GATE_FAILED";
  case ErrorCode::BenchmarkEnvironmentInvalid:
    return "BENCHMARK_ENVIRONMENT_INVALID";
  case ErrorCode::BenchmarkWorkerCrashed:
    return "BENCHMARK_WORKER_CRASHED";
  case ErrorCode::BenchmarkTimeout:
    return "BENCHMARK_TIMEOUT";
  case ErrorCode::ProfileIncompatible:
    return "PROFILE_INCOMPATIBLE";
  case ErrorCode::ProfileWarmupFailed:
    return "PROFILE_WARMUP_FAILED";
  case ErrorCode::NoEligibleProfile:
    return "NO_ELIGIBLE_PROFILE";
  case ErrorCode::InputStale:
    return "INPUT_STALE";
  case ErrorCode::InputUnsupported:
    return "INPUT_UNSUPPORTED";
  case ErrorCode::InferenceFailed:
    return "INFERENCE_FAILED";
  case ErrorCode::PostprocessFailed:
    return "POSTPROCESS_FAILED";
  case ErrorCode::ResourceExhausted:
    return "RESOURCE_EXHAUSTED";
  case ErrorCode::TelemetryUnavailable:
    return "TELEMETRY_UNAVAILABLE";
  case ErrorCode::RosLifecycleError:
    return "ROS_LIFECYCLE_ERROR";
  case ErrorCode::AuthRequired:
    return "AUTH_REQUIRED";
  case ErrorCode::AuthInvalid:
    return "AUTH_INVALID";
  case ErrorCode::DatabaseError:
    return "DATABASE_ERROR";
  case ErrorCode::InternalInvariantFailed:
    return "INTERNAL_INVARIANT_FAILED";
  }
  return "INTERNAL_INVARIANT_FAILED";
}

struct Error {
  ErrorCode code{ErrorCode::InternalInvariantFailed};
  std::string message;
  std::string remediation;
  std::string correlation_id;
  bool retryable{false};
  std::vector<std::string> causes;

  static Error make(ErrorCode c, std::string msg, std::string rem = {}, bool retry = false) {
    Error e;
    e.code = c;
    e.message = std::move(msg);
    e.remediation = std::move(rem);
    e.retryable = retry;
    return e;
  }
};

} // namespace perceptshift
