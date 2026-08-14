#include "perceptshift/image/preprocess_config.hpp"

namespace perceptshift::image {
namespace {

[[nodiscard]] Result<PixelFormat> parse_format_required(const std::string& s) {
  PixelFormat fmt{};
  if (!parse_pixel_format(s, fmt)) {
    return Error::make(ErrorCode::ConfigInvalid, "unsupported source pixel format: " + s,
                       "Use rgb8, bgr8, rgba8, bgra8, or mono8");
  }
  return fmt;
}

} // namespace

Result<PreprocessConfig> preprocess_config_from_json(const nlohmann::json& doc) {
  PreprocessConfig cfg;
  if (!doc.is_object()) {
    return Error::make(ErrorCode::ConfigInvalid, "preprocess contract must be an object");
  }

  // Nested expected_input is not a complete runtime contract; require canonical fields or
  // flat width/height aliases for transitional manifests.
  if (doc.contains("expected_input") && !doc.contains("input_width") && !doc.contains("width")) {
    return Error::make(
        ErrorCode::ConfigInvalid,
        "preprocess.expected_input alone is not a complete runtime contract",
        "Provide canonical preprocess fields: input_width, input_height, input_layout, ...");
  }

  cfg.width = doc.value("input_width", doc.value("width", cfg.width));
  cfg.height = doc.value("input_height", doc.value("height", cfg.height));
  if (cfg.width == 0 || cfg.height == 0) {
    return Error::make(ErrorCode::ConfigInvalid, "preprocess requires positive input_width/height");
  }

  const std::string layout = doc.value("input_layout", doc.value("layout", "nchw"));
  if (layout == "nhwc") {
    cfg.layout = TensorLayout::Nhwc;
  } else if (layout == "nchw") {
    cfg.layout = TensorLayout::Nchw;
  } else {
    return Error::make(ErrorCode::ConfigInvalid, "unsupported input_layout: " + layout);
  }

  const std::string backend = doc.value("backend", "neon_auto");
  if (backend == "scalar") {
    cfg.backend = PreprocessBackend::Scalar;
  } else if (backend == "neon") {
    cfg.backend = PreprocessBackend::NeonForced;
  } else if (backend == "neon_auto") {
    cfg.backend = PreprocessBackend::NeonAuto;
  } else {
    return Error::make(ErrorCode::ConfigInvalid, "unsupported preprocess backend: " + backend);
  }

  cfg.scale = doc.value("scale", cfg.scale);
  cfg.swap_rb = doc.value("swap_rb", cfg.swap_rb);
  cfg.output_dtype = doc.value("output_dtype", cfg.output_dtype);
  if (cfg.output_dtype != "float32") {
    return Error::make(ErrorCode::ConfigInvalid, "v1 preprocess output_dtype must be float32");
  }

  const std::string resize_mode = doc.value("resize_mode", "stretch");
  if (resize_mode != "stretch") {
    return Error::make(ErrorCode::ConfigInvalid,
                       "unsupported resize_mode: " + resize_mode + " (v1 supports stretch only)");
  }
  cfg.resize_mode = ResizeMode::Stretch;

  const std::string interp = doc.value("resize_interpolation", "bilinear");
  if (interp != "bilinear") {
    return Error::make(ErrorCode::ConfigInvalid, "unsupported resize_interpolation: " + interp);
  }
  cfg.resize_interpolation = ResizeInterpolation::Bilinear;

  const std::string color_handling =
      doc.value("source_color_handling", "convert_to_rgb");
  if (color_handling == "preserve") {
    cfg.source_color_handling = SourceColorHandling::Preserve;
  } else if (color_handling == "convert_to_rgb") {
    cfg.source_color_handling = SourceColorHandling::ConvertToRgb;
  } else {
    return Error::make(ErrorCode::ConfigInvalid,
                       "unsupported source_color_handling: " + color_handling);
  }

  if (doc.contains("mean")) {
    if (!doc["mean"].is_array() || doc["mean"].size() != 3) {
      return Error::make(ErrorCode::ConfigInvalid, "preprocess.mean must be length-3 array");
    }
    cfg.mean = {doc["mean"][0].get<float>(), doc["mean"][1].get<float>(),
                doc["mean"][2].get<float>()};
  }
  if (doc.contains("std")) {
    if (!doc["std"].is_array() || doc["std"].size() != 3) {
      return Error::make(ErrorCode::ConfigInvalid, "preprocess.std must be length-3 array");
    }
    cfg.std = {doc["std"][0].get<float>(), doc["std"][1].get<float>(),
               doc["std"][2].get<float>()};
  }

  if (doc.contains("accepted_source_formats")) {
    if (!doc["accepted_source_formats"].is_array() || doc["accepted_source_formats"].empty()) {
      return Error::make(ErrorCode::ConfigInvalid, "accepted_source_formats must be a non-empty array");
    }
    cfg.accepted_source_formats.clear();
    for (const auto& item : doc["accepted_source_formats"]) {
      auto fmt = parse_format_required(item.get<std::string>());
      if (!fmt) {
        return fmt.error();
      }
      cfg.accepted_source_formats.push_back(fmt.value());
    }
  }

  if (doc.contains("letterbox_pad_value") && !doc["letterbox_pad_value"].is_null()) {
    return Error::make(ErrorCode::ConfigInvalid,
                       "letterbox_pad_value must be null when resize_mode is stretch");
  }

  // Reject obsolete color_order when it would silently diverge from swap_rb.
  if (doc.contains("color_order")) {
    const std::string order = doc["color_order"].get<std::string>();
    if (order == "bgr" && !cfg.swap_rb) {
      return Error::make(ErrorCode::ConfigInvalid,
                         "obsolete color_order=bgr conflicts with swap_rb=false; use swap_rb=true");
    }
  }

  return cfg;
}

nlohmann::json preprocess_config_to_json(const PreprocessConfig& cfg) {
  nlohmann::json formats = nlohmann::json::array();
  for (auto fmt : cfg.accepted_source_formats) {
    formats.push_back(to_string(fmt));
  }
  return nlohmann::json{
      {"input_width", cfg.width},
      {"input_height", cfg.height},
      {"input_layout", cfg.layout == TensorLayout::Nhwc ? "nhwc" : "nchw"},
      {"accepted_source_formats", formats},
      {"source_color_handling",
       cfg.source_color_handling == SourceColorHandling::Preserve ? "preserve" : "convert_to_rgb"},
      {"resize_mode", "stretch"},
      {"resize_interpolation", "bilinear"},
      {"scale", cfg.scale},
      {"mean", cfg.mean},
      {"std", cfg.std},
      {"swap_rb", cfg.swap_rb},
      {"letterbox_pad_value", nullptr},
      {"output_dtype", cfg.output_dtype},
      {"backend", cfg.backend == PreprocessBackend::Scalar
                      ? "scalar"
                      : (cfg.backend == PreprocessBackend::NeonForced ? "neon" : "neon_auto")},
  };
}

PreprocessTransform make_stretch_transform(std::size_t source_w, std::size_t source_h,
                                           std::size_t model_w, std::size_t model_h) {
  PreprocessTransform t;
  t.resize_mode = ResizeMode::Stretch;
  t.source_width = source_w;
  t.source_height = source_h;
  t.model_width = model_w;
  t.model_height = model_h;
  t.pad_x = 0.f;
  t.pad_y = 0.f;
  t.scale_x = (source_w > 0 && model_w > 0)
                  ? static_cast<float>(model_w) / static_cast<float>(source_w)
                  : 1.f;
  t.scale_y = (source_h > 0 && model_h > 0)
                  ? static_cast<float>(model_h) / static_cast<float>(source_h)
                  : 1.f;
  return t;
}

} // namespace perceptshift::image
