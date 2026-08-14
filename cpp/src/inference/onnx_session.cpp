#include "perceptshift/crypto/digest.hpp"
#include "perceptshift/inference/session_factory.hpp"
#include "perceptshift/util/steady_clock.hpp"

#include <algorithm>
#include <cstring>
#include <limits>
#include <memory>
#include <mutex>
#include <unordered_map>
#include <utility>

#if defined(PERCEPTSHIFT_HAS_ONNXRUNTIME) && PERCEPTSHIFT_HAS_ONNXRUNTIME
#include <onnxruntime_cxx_api.h>
#include <onnxruntime_session_options_config_keys.h>
#endif

namespace perceptshift::inference {
namespace {

#if defined(PERCEPTSHIFT_HAS_ONNXRUNTIME) && PERCEPTSHIFT_HAS_ONNXRUNTIME

Ort::Env& shared_ort_env() {
  static Ort::Env env(ORT_LOGGING_LEVEL_WARNING, "perceptshift");
  return env;
}

std::size_t element_byte_width(ONNXTensorElementDataType t) {
  switch (t) {
  case ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT:
    return 4;
  case ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT16:
    return 2;
  case ONNX_TENSOR_ELEMENT_DATA_TYPE_INT8:
  case ONNX_TENSOR_ELEMENT_DATA_TYPE_UINT8:
  case ONNX_TENSOR_ELEMENT_DATA_TYPE_BOOL:
    return 1;
  case ONNX_TENSOR_ELEMENT_DATA_TYPE_INT32:
    return 4;
  case ONNX_TENSOR_ELEMENT_DATA_TYPE_INT64:
    return 8;
  default:
    return 0;
  }
}

ElementType from_ort(ONNXTensorElementDataType t) {
  switch (t) {
  case ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT:
    return ElementType::Float32;
  case ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT16:
    return ElementType::Float16;
  case ONNX_TENSOR_ELEMENT_DATA_TYPE_INT8:
    return ElementType::Int8;
  case ONNX_TENSOR_ELEMENT_DATA_TYPE_UINT8:
    return ElementType::UInt8;
  case ONNX_TENSOR_ELEMENT_DATA_TYPE_INT32:
    return ElementType::Int32;
  case ONNX_TENSOR_ELEMENT_DATA_TYPE_INT64:
    return ElementType::Int64;
  case ONNX_TENSOR_ELEMENT_DATA_TYPE_BOOL:
    return ElementType::Bool;
  default:
    return ElementType::Unknown;
  }
}

ONNXTensorElementDataType to_ort_type(const std::string& name) {
  if (name == "float32" || name == "float")
    return ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT;
  if (name == "float16")
    return ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT16;
  if (name == "int8")
    return ONNX_TENSOR_ELEMENT_DATA_TYPE_INT8;
  if (name == "uint8")
    return ONNX_TENSOR_ELEMENT_DATA_TYPE_UINT8;
  if (name == "int32")
    return ONNX_TENSOR_ELEMENT_DATA_TYPE_INT32;
  if (name == "int64")
    return ONNX_TENSOR_ELEMENT_DATA_TYPE_INT64;
  if (name == "bool")
    return ONNX_TENSOR_ELEMENT_DATA_TYPE_BOOL;
  return ONNX_TENSOR_ELEMENT_DATA_TYPE_UNDEFINED;
}

Result<std::size_t> byte_size_for_shape(const std::vector<std::int64_t>& shape,
                                        std::size_t elem_bytes) {
  if (elem_bytes == 0) {
    return Err<std::size_t>(ErrorCode::ModelTensorMismatch,
                            "unsupported tensor element type width");
  }
  std::size_t elems = 1;
  for (auto d : shape) {
    if (d < 0) {
      return Err<std::size_t>(ErrorCode::ModelTensorMismatch,
                              "unresolved dynamic dimension in tensor shape");
    }
    if (d == 0) {
      return Err<std::size_t>(ErrorCode::ModelTensorMismatch,
                              "zero dimension is invalid for inference tensors");
    }
    const auto ud = static_cast<std::size_t>(d);
    if (elems != 0 && ud > (std::numeric_limits<std::size_t>::max() / elems)) {
      return Err<std::size_t>(ErrorCode::ResourceExhausted, "tensor element count overflow");
    }
    elems *= ud;
  }
  if (elems != 0 && elem_bytes > (std::numeric_limits<std::size_t>::max() / elems)) {
    return Err<std::size_t>(ErrorCode::ResourceExhausted, "tensor byte size overflow");
  }
  return Ok(elems * elem_bytes);
}

class OrtSessionImpl final : public OnnxSession {
public:
  OrtSessionImpl(Ort::Session session, ModelMetadata meta, SessionOptions options,
                 ExecutionProviderReport report, std::vector<std::string> input_names,
                 std::vector<std::string> output_names)
      : session_(std::move(session)), meta_(std::move(meta)), options_(std::move(options)),
        report_(std::move(report)), input_names_(std::move(input_names)),
        output_names_(std::move(output_names)) {}

  const ModelMetadata& metadata() const override { return meta_; }

  Result<InferenceResult> run(const InferenceRequest& request) override {
    try {
      if (request.inputs.size() != meta_.inputs.size()) {
        return Err<InferenceResult>(ErrorCode::ModelTensorMismatch, "input count mismatch");
      }

      Ort::MemoryInfo mem = Ort::MemoryInfo::CreateCpu(OrtArenaAllocator, OrtMemTypeDefault);
      // Independent stable storage for each input — pointers must remain valid through Run.
      std::vector<std::vector<std::uint8_t>> owned_copies;
      owned_copies.reserve(request.inputs.size());
      std::vector<Ort::Value> inputs;
      std::vector<const char*> input_name_ptrs;
      inputs.reserve(request.inputs.size());
      input_name_ptrs.reserve(request.inputs.size());

      for (std::size_t i = 0; i < request.inputs.size(); ++i) {
        const auto& t = request.inputs[i];
        if (t.name != meta_.inputs[i].name && t.name != input_names_[i]) {
          return Err<InferenceResult>(ErrorCode::ModelTensorMismatch,
                                      "wrong input name: expected " + meta_.inputs[i].name);
        }
        if (t.shape.size() != meta_.inputs[i].shape.size()) {
          return Err<InferenceResult>(ErrorCode::ModelTensorMismatch,
                                      "wrong input rank for " + t.name);
        }
        for (std::size_t d = 0; d < t.shape.size(); ++d) {
          const auto expected = meta_.inputs[i].shape[d];
          if (expected >= 0 && t.shape[d] != expected) {
            return Err<InferenceResult>(ErrorCode::ModelTensorMismatch,
                                        "input shape mismatch for " + t.name);
          }
          if (t.shape[d] < 0) {
            return Err<InferenceResult>(ErrorCode::ModelTensorMismatch,
                                        "negative unresolved dimension in request");
          }
        }

        auto ort_type = to_ort_type(t.element_type);
        if (ort_type == ONNX_TENSOR_ELEMENT_DATA_TYPE_UNDEFINED) {
          // Fall back to model metadata type for float32 adapters.
          ort_type = ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT;
          if (meta_.inputs[i].element_type == ElementType::Int8) {
            ort_type = ONNX_TENSOR_ELEMENT_DATA_TYPE_INT8;
          } else if (meta_.inputs[i].element_type == ElementType::UInt8) {
            ort_type = ONNX_TENSOR_ELEMENT_DATA_TYPE_UINT8;
          } else if (meta_.inputs[i].element_type == ElementType::Int32) {
            ort_type = ONNX_TENSOR_ELEMENT_DATA_TYPE_INT32;
          } else if (meta_.inputs[i].element_type == ElementType::Int64) {
            ort_type = ONNX_TENSOR_ELEMENT_DATA_TYPE_INT64;
          }
        }
        const auto width = element_byte_width(ort_type);
        auto expected_bytes = byte_size_for_shape(t.shape, width);
        if (!expected_bytes) {
          return Err<InferenceResult>(expected_bytes.error());
        }
        if (t.data == nullptr) {
          return Err<InferenceResult>(ErrorCode::ModelTensorMismatch, "null input buffer");
        }
        if (t.byte_size != expected_bytes.value()) {
          return Err<InferenceResult>(ErrorCode::ModelTensorMismatch,
                                      "input buffer byte size mismatch for " + t.name + ": got " +
                                          std::to_string(t.byte_size) + " expected " +
                                          std::to_string(expected_bytes.value()));
        }

        owned_copies.emplace_back(static_cast<const std::uint8_t*>(t.data),
                                  static_cast<const std::uint8_t*>(t.data) + t.byte_size);
        input_name_ptrs.push_back(input_names_[i].c_str());
        inputs.emplace_back(Ort::Value::CreateTensor(mem, owned_copies.back().data(),
                                                     owned_copies.back().size(), t.shape.data(),
                                                     t.shape.size(), ort_type));
      }

      std::vector<const char*> output_name_ptrs;
      output_name_ptrs.reserve(output_names_.size());
      for (const auto& n : output_names_) {
        output_name_ptrs.push_back(n.c_str());
      }

      const auto start = util::steady_now_ns();
      auto outputs = session_.Run(Ort::RunOptions{nullptr}, input_name_ptrs.data(), inputs.data(),
                                  inputs.size(), output_name_ptrs.data(), output_name_ptrs.size());
      const auto end = util::steady_now_ns();

      InferenceResult result;
      result.inference_start_steady_ns = start;
      result.inference_end_steady_ns = end;
      result.active_provider_summary = report_.registered_providers.empty()
                                           ? "CPUExecutionProvider"
                                           : report_.registered_providers.front();
      for (std::size_t i = 0; i < outputs.size(); ++i) {
        NamedTensor nt;
        nt.name = output_names_[i];
        auto info = outputs[i].GetTensorTypeAndShapeInfo();
        nt.shape = info.GetShape();
        const auto ort_t = info.GetElementType();
        nt.element_type = to_string(from_ort(ort_t));
        const auto count = info.GetElementCount();
        const auto width = element_byte_width(ort_t);
        if (width == 0) {
          return Err<InferenceResult>(ErrorCode::ModelTensorMismatch,
                                      "unsupported output element type");
        }
        if (count > (std::numeric_limits<std::size_t>::max() / width)) {
          return Err<InferenceResult>(ErrorCode::ResourceExhausted, "output byte size overflow");
        }
        const std::size_t bytes = static_cast<std::size_t>(count) * width;
        const void* raw = outputs[i].GetTensorRawData();
        nt.data.resize(bytes);
        std::memcpy(nt.data.data(), raw, bytes);
        result.outputs.push_back(std::move(nt));
      }
      return Ok(std::move(result));
    } catch (const Ort::Exception& ex) {
      return Err<InferenceResult>(ErrorCode::InferenceFailed, ex.what());
    } catch (const std::exception& ex) {
      return Err<InferenceResult>(ErrorCode::InferenceFailed, ex.what());
    }
  }

  Result<void> warmup(int iterations) override {
    if (iterations < 0) {
      return Err(ErrorCode::ConfigInvalid, "warmup iterations must be non-negative");
    }
    std::vector<std::vector<std::uint8_t>> scratch_bufs(meta_.inputs.size());
    for (int iter = 0; iter < iterations; ++iter) {
      InferenceRequest req;
      req.inputs.reserve(meta_.inputs.size());
      for (std::size_t i = 0; i < meta_.inputs.size(); ++i) {
        const auto& spec = meta_.inputs[i];
        NamedTensorView view;
        view.name = spec.name;
        view.shape = spec.shape;
        for (auto& d : view.shape) {
          if (d < 0) {
            return Err(ErrorCode::ProfileWarmupFailed,
                       "warmup requires resolved dynamic dimensions from profile configuration");
          }
        }
        ONNXTensorElementDataType ort_t = ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT;
        switch (spec.element_type) {
        case ElementType::Float32:
          ort_t = ONNX_TENSOR_ELEMENT_DATA_TYPE_FLOAT;
          break;
        case ElementType::Int8:
          ort_t = ONNX_TENSOR_ELEMENT_DATA_TYPE_INT8;
          break;
        case ElementType::UInt8:
          ort_t = ONNX_TENSOR_ELEMENT_DATA_TYPE_UINT8;
          break;
        case ElementType::Int32:
          ort_t = ONNX_TENSOR_ELEMENT_DATA_TYPE_INT32;
          break;
        case ElementType::Int64:
          ort_t = ONNX_TENSOR_ELEMENT_DATA_TYPE_INT64;
          break;
        default:
          return Err(ErrorCode::ProfileWarmupFailed, "unsupported input type for warmup");
        }
        auto bytes = byte_size_for_shape(view.shape, element_byte_width(ort_t));
        if (!bytes) {
          return Err(bytes.error());
        }
        scratch_bufs[i].assign(bytes.value(), 0);
        view.data = scratch_bufs[i].data();
        view.byte_size = scratch_bufs[i].size();
        view.element_type = to_string(spec.element_type);
        req.inputs.push_back(view);
      }
      auto r = run(req);
      if (!r) {
        return Err(ErrorCode::ProfileWarmupFailed, r.error().message);
      }
    }
    return Ok();
  }

  ExecutionProviderReport provider_report() const override { return report_; }

private:
  Ort::Session session_;
  ModelMetadata meta_;
  SessionOptions options_;
  ExecutionProviderReport report_;
  std::vector<std::string> input_names_;
  std::vector<std::string> output_names_;
};

Result<void> validate_contract(const ModelMetadata& meta, const SessionCreateRequest& request) {
  if (!request.expected_inputs.empty()) {
    if (meta.inputs.size() != request.expected_inputs.size()) {
      return Err(ErrorCode::ModelTensorMismatch, "input count mismatch");
    }
    for (std::size_t i = 0; i < meta.inputs.size(); ++i) {
      if (meta.inputs[i].name != request.expected_inputs[i].name) {
        return Err(ErrorCode::ModelTensorMismatch, "input name mismatch: " + meta.inputs[i].name);
      }
    }
  }
  if (!request.expected_outputs.empty()) {
    if (meta.outputs.size() != request.expected_outputs.size()) {
      return Err(ErrorCode::ModelTensorMismatch, "output count mismatch");
    }
    for (std::size_t i = 0; i < meta.outputs.size(); ++i) {
      if (meta.outputs[i].name != request.expected_outputs[i].name) {
        return Err(ErrorCode::ModelTensorMismatch, "output name mismatch: " + meta.outputs[i].name);
      }
    }
  }
  return Ok();
}

Result<void> apply_session_options(Ort::SessionOptions& opts, const SessionOptions& options,
                                   ExecutionProviderReport& report) {
  if (options.intra_op_threads < 1 || options.inter_op_threads < 1) {
    return Err(ErrorCode::ConfigInvalid, "thread counts must be >= 1");
  }
  opts.SetIntraOpNumThreads(options.intra_op_threads);
  opts.SetInterOpNumThreads(options.inter_op_threads);
  opts.SetExecutionMode(ORT_SEQUENTIAL);
  opts.EnableMemPattern();
  opts.EnableCpuMemArena();

  if (options.allow_intra_op_spinning) {
    opts.AddConfigEntry(kOrtSessionOptionsConfigAllowIntraOpSpinning, "1");
  } else {
    opts.AddConfigEntry(kOrtSessionOptionsConfigAllowIntraOpSpinning, "0");
  }

  if (options.graph_optimization_level == "all") {
    opts.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_ALL);
  } else if (options.graph_optimization_level == "extended") {
    opts.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_EXTENDED);
  } else if (options.graph_optimization_level == "basic") {
    opts.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_ENABLE_BASIC);
  } else if (options.graph_optimization_level == "disabled" ||
             options.graph_optimization_level == "none") {
    opts.SetGraphOptimizationLevel(GraphOptimizationLevel::ORT_DISABLE_ALL);
  } else {
    return Err(ErrorCode::ConfigInvalid,
               "unknown graph_optimization_level: " + options.graph_optimization_level);
  }

  report.provider_order = options.provider_order;
  report.requested_providers = options.provider_order;
  bool require_xnnpack = false;
  bool registered_xnnpack = false;
  for (const auto& provider : options.provider_order) {
    if (provider == "CPUExecutionProvider" || provider == "CPU") {
      report.registered_providers.push_back("CPUExecutionProvider");
      continue;
    }
    if (provider == "XNNPACKExecutionProvider" || provider == "XNNPACK") {
      require_xnnpack = true;
      try {
        std::unordered_map<std::string, std::string> xnn_opts;
        xnn_opts["intra_op_num_threads"] =
            std::to_string(std::max(1, options.xnnpack_intra_op_threads));
        opts.AppendExecutionProvider("XNNPACK", xnn_opts);
        report.registered_providers.push_back("XNNPACKExecutionProvider");
        registered_xnnpack = true;
      } catch (const Ort::Exception& ex) {
        report.warnings.push_back(std::string("XNNPACK registration failed: ") + ex.what());
        report.xnnpack_fraction_unavailable_reason = "XNNPACK_REGISTRATION_FAILED";
      }
      continue;
    }
    return Err(ErrorCode::ConfigInvalid, "unknown execution provider: " + provider);
  }

  if (require_xnnpack && !registered_xnnpack) {
    // Required by profile order — reject rather than silently fall back.
    const bool xnnpack_optional =
        std::find(options.provider_order.begin(), options.provider_order.end(),
                  "CPUExecutionProvider") != options.provider_order.end() ||
        std::find(options.provider_order.begin(), options.provider_order.end(), "CPU") !=
            options.provider_order.end();
    if (!xnnpack_optional) {
      return Err(ErrorCode::ModelProviderUnavailable,
                 "XNNPACK was required but could not be registered",
                 "Build/install ONNX Runtime with XNNPACK or change provider_order");
    }
    report.warnings.push_back("XNNPACK optional; falling back to CPUExecutionProvider");
    if (std::find(report.registered_providers.begin(), report.registered_providers.end(),
                  "CPUExecutionProvider") == report.registered_providers.end()) {
      report.registered_providers.push_back("CPUExecutionProvider");
    }
  }

  if (report.xnnpack_fraction_unavailable_reason.empty()) {
    report.xnnpack_fraction_unavailable_reason = "NODE_ASSIGNMENT_NOT_COMPUTED";
  }
  return Ok();
}

#endif

} // namespace

bool onnxruntime_available() noexcept {
#if defined(PERCEPTSHIFT_HAS_ONNXRUNTIME) && PERCEPTSHIFT_HAS_ONNXRUNTIME
  return true;
#else
  return false;
#endif
}

Result<std::unique_ptr<OnnxSession>> create_onnx_session(const SessionCreateRequest& request) {
  auto secure = util::validate_model_path(request.model_path, request.security);
  if (!secure) {
    return Err<std::unique_ptr<OnnxSession>>(secure.error());
  }
  if (request.expected_sha256.has_value()) {
    auto dig = crypto::sha256_file_hex(request.model_path);
    if (!dig) {
      return Err<std::unique_ptr<OnnxSession>>(dig.error());
    }
    if (dig.value() != *request.expected_sha256) {
      return Err<std::unique_ptr<OnnxSession>>(ErrorCode::FileIntegrityFailed,
                                               "model SHA-256 mismatch");
    }
  }

#if defined(PERCEPTSHIFT_HAS_ONNXRUNTIME) && PERCEPTSHIFT_HAS_ONNXRUNTIME
  try {
    Ort::SessionOptions opts;
    ExecutionProviderReport report;
    auto applied = apply_session_options(opts, request.options, report);
    if (!applied) {
      return Err<std::unique_ptr<OnnxSession>>(applied.error());
    }

    Ort::Session session(shared_ort_env(), request.model_path.c_str(), opts);
    ModelMetadata meta;
    meta.model_path = request.model_path.string();
    if (request.expected_sha256) {
      meta.model_sha256 = *request.expected_sha256;
    } else {
      auto dig = crypto::sha256_file_hex(request.model_path);
      if (dig) {
        meta.model_sha256 = dig.value();
      }
    }
    meta.onnxruntime_version = OrtGetApiBase()->GetVersionString();
    Ort::AllocatorWithDefaultOptions allocator;
    std::vector<std::string> input_names;
    std::vector<std::string> output_names;
    const auto in_count = session.GetInputCount();
    for (std::size_t i = 0; i < in_count; ++i) {
      TensorSpec spec;
      auto name = session.GetInputNameAllocated(i, allocator);
      spec.name = name.get();
      input_names.push_back(spec.name);
      auto type_info = session.GetInputTypeInfo(i);
      auto tensor = type_info.GetTensorTypeAndShapeInfo();
      spec.element_type = from_ort(tensor.GetElementType());
      spec.shape = tensor.GetShape();
      meta.inputs.push_back(std::move(spec));
    }
    const auto out_count = session.GetOutputCount();
    for (std::size_t i = 0; i < out_count; ++i) {
      TensorSpec spec;
      auto name = session.GetOutputNameAllocated(i, allocator);
      spec.name = name.get();
      output_names.push_back(spec.name);
      auto type_info = session.GetOutputTypeInfo(i);
      auto tensor = type_info.GetTensorTypeAndShapeInfo();
      spec.element_type = from_ort(tensor.GetElementType());
      spec.shape = tensor.GetShape();
      meta.outputs.push_back(std::move(spec));
    }
    meta.available_providers = Ort::GetAvailableProviders();
    auto contract = validate_contract(meta, request);
    if (!contract) {
      return Err<std::unique_ptr<OnnxSession>>(contract.error());
    }
    return Ok(std::unique_ptr<OnnxSession>(
        new OrtSessionImpl(std::move(session), std::move(meta), request.options, std::move(report),
                           std::move(input_names), std::move(output_names))));
  } catch (const Ort::Exception& ex) {
    return Err<std::unique_ptr<OnnxSession>>(ErrorCode::ModelInvalid, ex.what());
  } catch (const std::exception& ex) {
    return Err<std::unique_ptr<OnnxSession>>(ErrorCode::ModelInvalid, ex.what());
  }
#else
  return Err<std::unique_ptr<OnnxSession>>(
      ErrorCode::ModelProviderUnavailable, "ONNX Runtime was not found at configure time",
      "Build with PERCEPTSHIFT_WITH_ONNXRUNTIME=ON and set PERCEPTSHIFT_ORT_ROOT");
#endif
}

} // namespace perceptshift::inference
