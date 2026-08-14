#include "perceptshift/runtime/profile_executor.hpp"

#include "perceptshift/image/pixel_format.hpp"
#include "perceptshift/image/raw_image_validation.hpp"
#include "perceptshift/util/steady_clock.hpp"

#include <algorithm>
#include <cstring>

namespace perceptshift::runtime {
namespace {

[[nodiscard]] Result<void> validate_image_payload(const ProfileExecutorInput& input,
                                                  image::PixelFormat fmt,
                                                  const image::PreprocessConfig& cfg) {
  return image::validate_raw_image_payload(input.payload.data(), input.payload.size(), input.width,
                                           input.height, input.stride_bytes, fmt, cfg);
}

[[nodiscard]] Result<std::vector<std::int64_t>>
resolve_fixed_or_concrete_shape(const std::vector<std::int64_t>& model_shape,
                                std::size_t element_count, bool allow_zeros_fill_dynamic) {
  if (model_shape.empty()) {
    return Error::make(ErrorCode::ModelTensorMismatch, "model input shape is empty");
  }
  std::vector<std::int64_t> shape = model_shape;
  std::vector<std::size_t> dynamic_idxs;
  std::size_t known = 1;
  bool has_known = false;
  for (std::size_t i = 0; i < shape.size(); ++i) {
    if (shape[i] < 0) {
      dynamic_idxs.push_back(i);
    } else if (shape[i] == 0) {
      return Error::make(ErrorCode::ModelTensorMismatch, "model input dimension is zero");
    } else {
      known *= static_cast<std::size_t>(shape[i]);
      has_known = true;
    }
  }
  if (dynamic_idxs.empty()) {
    if (element_count != known) {
      return Error::make(ErrorCode::ModelTensorMismatch,
                         "tensor element count " + std::to_string(element_count) +
                             " does not match fixed model shape product " + std::to_string(known));
    }
    return shape;
  }
  if (allow_zeros_fill_dynamic) {
    for (auto idx : dynamic_idxs) {
      shape[idx] = 1;
    }
    return shape;
  }
  if (dynamic_idxs.size() != 1 || !has_known || known == 0 || (element_count % known) != 0) {
    return Error::make(ErrorCode::ModelTensorMismatch,
                       "ambiguous unresolved dynamic dimensions; refusing to invent shape",
                       "Provide a fixed-shape model or a tensor whose size resolves exactly one "
                       "dynamic dimension");
  }
  shape[dynamic_idxs[0]] = static_cast<std::int64_t>(element_count / known);
  if (shape[dynamic_idxs[0]] <= 0) {
    return Error::make(ErrorCode::ModelTensorMismatch, "resolved dynamic dimension is non-positive");
  }
  return shape;
}

} // namespace

ProfileExecutor::ProfileExecutor(inference::OnnxSession* session, adapters::Adapter* adapter,
                                 image::PreprocessConfig preprocess)
    : session_(session), adapter_(adapter), preprocess_(std::move(preprocess)) {}

Result<ProfileExecutorResult> ProfileExecutor::execute(const ProfileExecutorInput& input) const {
  ProfileExecutorResult result;
  const auto t0 = util::steady_now_ns();
  if (session_ == nullptr) {
    result.error = Error::make(ErrorCode::ConfigInvalid, "ProfileExecutor missing session");
    return result;
  }
  const auto& meta = session_->metadata();
  if (meta.inputs.empty()) {
    result.error = Error::make(ErrorCode::ModelTensorMismatch, "model has no inputs");
    return result;
  }
  if (meta.inputs.size() != 1) {
    result.error = Error::make(ErrorCode::ModelTensorMismatch,
                               "v1 ProfileExecutor supports single-input models only; found " +
                                   std::to_string(meta.inputs.size()),
                               "Reject multi-input models during Forge validation or provide an "
                               "explicit multi-input binding contract");
    return result;
  }
  if (meta.inputs[0].element_type != inference::ElementType::Float32 &&
      meta.inputs[0].element_type != inference::ElementType::Unknown) {
    result.error = Error::make(ErrorCode::ModelTensorMismatch,
                               "unsupported model input element type: " +
                                   inference::to_string(meta.inputs[0].element_type),
                               "v1 requires float32 inputs");
    return result;
  }

  std::vector<std::uint8_t> owned;
  inference::InferenceRequest ireq;
  ireq.sequence_id = input.sequence_id;
  ireq.trace_id = input.trace_id;
  ireq.source_timestamp_ns = input.source_timestamp_ns;
  ireq.receive_steady_ns =
      input.receive_steady_ns > 0 ? input.receive_steady_ns : util::steady_now_ns();

  if (input.kind == ProfileExecutorInput::Kind::ZerosSmoke) {
    if (!input.allow_zeros_smoke) {
      result.error = Error::make(ErrorCode::InputUnsupported,
                                 "zeros smoke input rejected outside named smoke mode");
      return result;
    }
    auto shape_r = resolve_fixed_or_concrete_shape(meta.inputs[0].shape, 0, true);
    if (!shape_r) {
      result.error = shape_r.error();
      return result;
    }
    auto shape = shape_r.value();
    std::size_t elems = 1;
    for (auto d : shape)
      elems *= static_cast<std::size_t>(d);
    owned.assign(elems * sizeof(float), 0);
    inference::NamedTensorView view;
    view.name = meta.inputs[0].name;
    view.shape = shape;
    view.data = owned.data();
    view.byte_size = owned.size();
    view.element_type = "float32";
    ireq.inputs.push_back(view);
    result.tensor_contract = {{"shape", shape}, {"element_type", "float32"}, {"zeros_smoke", true}};
  } else if (input.kind == ProfileExecutorInput::Kind::TensorBytes) {
    if (input.payload.empty()) {
      result.error = Error::make(ErrorCode::DatasetInvalid, "tensor sample payload is empty");
      return result;
    }
    if ((input.payload.size() % sizeof(float)) != 0) {
      result.error = Error::make(ErrorCode::ModelTensorMismatch, "tensor bytes not float32 aligned");
      return result;
    }
    const std::size_t elems = input.payload.size() / sizeof(float);
    auto shape_r = resolve_fixed_or_concrete_shape(meta.inputs[0].shape, elems, false);
    if (!shape_r) {
      result.error = shape_r.error();
      return result;
    }
    owned = input.payload;
    inference::NamedTensorView view;
    view.name = meta.inputs[0].name;
    view.shape = shape_r.value();
    view.data = owned.data();
    view.byte_size = owned.size();
    view.element_type = "float32";
    ireq.inputs.push_back(view);
    result.tensor_contract = {{"shape", view.shape}, {"element_type", "float32"}};
  } else if (input.kind == ProfileExecutorInput::Kind::RawImageBytes) {
    image::PixelFormat fmt{};
    if (!image::parse_pixel_format(input.pixel_format, fmt)) {
      result.error = Error::make(ErrorCode::InputUnsupported,
                                 "unsupported pixel_format: " + input.pixel_format);
      return result;
    }
    auto valid = validate_image_payload(input, fmt, preprocess_);
    if (!valid) {
      result.error = valid.error();
      return result;
    }
    image::ImageView image;
    image.data = input.payload.data();
    image.width = input.width;
    image.height = input.height;
    image.stride_bytes =
        input.stride_bytes > 0 ? input.stride_bytes
                               : input.width * static_cast<std::size_t>(image::channel_count(fmt));
    image.format = fmt;

    image::TensorBuffer tensor;
    const auto t_pre0 = util::steady_now_ns();
    auto pre = image::preprocess_to_float_tensor(image, preprocess_, tensor);
    const auto t_pre1 = util::steady_now_ns();
    result.preprocess_ms = static_cast<double>(t_pre1 - t_pre0) / 1.0e6;
    if (!pre) {
      result.error = pre.error();
      return result;
    }
    result.preprocess_impl =
        pre.value().impl == image::PreprocessImplUsed::Neon ? "neon" : "scalar";
    result.transform = image::make_stretch_transform(input.width, input.height, preprocess_.width,
                                                     preprocess_.height);

    owned.resize(tensor.size() * sizeof(float));
    if (!owned.empty()) {
      std::memcpy(owned.data(), tensor.data(), owned.size());
    }
    const std::size_t elems = tensor.size();
    auto shape_r = resolve_fixed_or_concrete_shape(meta.inputs[0].shape, elems, false);
    if (!shape_r) {
      // If model shape is fully dynamic / mismatched, still enforce exact element count from
      // canonical preprocess output against declared preprocess contract.
      std::vector<std::int64_t> fallback;
      if (preprocess_.layout == image::TensorLayout::Nchw) {
        fallback = {1, 3, static_cast<std::int64_t>(preprocess_.height),
                    static_cast<std::int64_t>(preprocess_.width)};
      } else {
        fallback = {1, static_cast<std::int64_t>(preprocess_.height),
                    static_cast<std::int64_t>(preprocess_.width), 3};
      }
      std::size_t expected = 1;
      for (auto d : fallback)
        expected *= static_cast<std::size_t>(d);
      if (elems != expected) {
        result.error = shape_r.error();
        return result;
      }
      shape_r = fallback;
    }
    inference::NamedTensorView view;
    view.name = meta.inputs[0].name;
    view.shape = shape_r.value();
    view.data = owned.data();
    view.byte_size = owned.size();
    view.element_type = "float32";
    ireq.inputs.push_back(view);
    result.tensor_contract = {
        {"shape", view.shape},
        {"element_type", "float32"},
        {"preprocess_impl", result.preprocess_impl},
        {"source_format", input.pixel_format},
    };
  } else {
    result.error = Error::make(ErrorCode::InputUnsupported, "unsupported ProfileExecutor input kind");
    return result;
  }

  auto infer = session_->run(ireq);
  if (!infer) {
    result.error = infer.error();
    return result;
  }
  result.inference_ms = static_cast<double>(infer.value().inference_end_steady_ns -
                                            infer.value().inference_start_steady_ns) /
                        1.0e6;
  result.active_provider_summary = infer.value().active_provider_summary;

  const auto t_post0 = util::steady_now_ns();
  if (!infer.value().outputs.empty() && adapter_ != nullptr) {
    adapters::TensorView tv;
    const auto& out0 = infer.value().outputs.front();
    if (out0.element_type == "float32" && (out0.data.size() % sizeof(float)) == 0) {
      tv.data = reinterpret_cast<const float*>(out0.data.data());
      tv.shape = out0.shape;
      auto normalized = adapter_->postprocess(tv);
      if (!normalized) {
        result.error = normalized.error();
        return result;
      }
      result.output = std::move(normalized.value());
      // Invert stretch resize for YOLO detections into source coordinates.
      if (result.output.task == "yolo_v8_detection" && result.transform.source_width > 0 &&
          result.transform.source_height > 0) {
        for (auto& det : result.output.detections) {
          if (result.transform.scale_x > 0.f) {
            det.x = (det.x - result.transform.pad_x) / result.transform.scale_x;
            det.w = det.w / result.transform.scale_x;
          }
          if (result.transform.scale_y > 0.f) {
            det.y = (det.y - result.transform.pad_y) / result.transform.scale_y;
            det.h = det.h / result.transform.scale_y;
          }
          const float max_x = static_cast<float>(result.transform.source_width);
          const float max_y = static_cast<float>(result.transform.source_height);
          det.x = std::clamp(det.x, 0.f, max_x);
          det.y = std::clamp(det.y, 0.f, max_y);
          det.w = std::clamp(det.w, 0.f, max_x);
          det.h = std::clamp(det.h, 0.f, max_y);
        }
      }
    }
  }
  const auto t_post1 = util::steady_now_ns();
  result.postprocess_ms = static_cast<double>(t_post1 - t_post0) / 1.0e6;
  result.executor_ms = static_cast<double>(t_post1 - t0) / 1.0e6;
  result.ok = true;
  return result;
}

} // namespace perceptshift::runtime
