#include "perceptshift/adapters/adapter_factory.hpp"

#include "perceptshift/adapters/classification_adapter.hpp"
#include "perceptshift/adapters/raw_tensor_adapter.hpp"
#include "perceptshift/adapters/yolo_v8_adapter.hpp"

namespace perceptshift::adapters {
namespace {

[[nodiscard]] Result<ClassificationAdapterConfig>
parse_classification_config(const nlohmann::json& config) {
  ClassificationAdapterConfig cfg;
  if (!config.is_object()) {
    return cfg;
  }
  cfg.top_k = config.value("top_k", cfg.top_k);
  cfg.score_threshold = config.value("score_threshold", cfg.score_threshold);
  const std::string semantics = config.value("output_semantics", "probabilities");
  if (semantics == "logits") {
    cfg.output_semantics = ClassificationOutputSemantics::Logits;
  } else if (semantics == "probabilities") {
    cfg.output_semantics = ClassificationOutputSemantics::Probabilities;
  } else {
    return Error::make(ErrorCode::ConfigInvalid,
                       "unsupported classification output_semantics: " + semantics);
  }
  if (cfg.top_k <= 0) {
    return Error::make(ErrorCode::ConfigInvalid, "classification top_k must be positive");
  }
  if (config.contains("labels") && config["labels"].is_object()) {
    for (auto it = config["labels"].begin(); it != config["labels"].end(); ++it) {
      cfg.labels[std::stoi(it.key())] = it.value().get<std::string>();
    }
  } else if (config.contains("labels") && config["labels"].is_array()) {
    int idx = 0;
    for (const auto& label : config["labels"]) {
      cfg.labels[idx++] = label.get<std::string>();
    }
  }
  return cfg;
}

[[nodiscard]] Result<YoloV8AdapterConfig> parse_yolo_config(const nlohmann::json& config) {
  YoloV8AdapterConfig cfg;
  if (!config.is_object()) {
    return cfg;
  }
  cfg.confidence_threshold = config.value("confidence_threshold", cfg.confidence_threshold);
  cfg.iou_threshold = config.value("iou_threshold", config.value("nms_threshold", cfg.iou_threshold));
  cfg.max_detections = config.value("max_detections", cfg.max_detections);
  if (config.contains("num_classes")) {
    cfg.num_classes = config.value("num_classes", cfg.num_classes);
  } else if (config.contains("class_count")) {
    cfg.num_classes = config.value("class_count", cfg.num_classes);
  }
  cfg.input_width = config.value("input_width", cfg.input_width);
  cfg.input_height = config.value("input_height", cfg.input_height);
  cfg.coordinate_space = config.value("coordinate_space", cfg.coordinate_space);
  cfg.output_layout = config.value("output_layout", cfg.output_layout);
  if (cfg.num_classes <= 0) {
    return Error::make(ErrorCode::ConfigInvalid, "yolo class_count/num_classes must be positive");
  }
  if (cfg.coordinate_space != "model_input_pixels" && cfg.coordinate_space != "normalized_0_1") {
    return Error::make(ErrorCode::ConfigInvalid,
                       "unsupported yolo coordinate_space: " + cfg.coordinate_space);
  }
  if (config.contains("labels") && config["labels"].is_object()) {
    for (auto it = config["labels"].begin(); it != config["labels"].end(); ++it) {
      cfg.labels[std::stoi(it.key())] = it.value().get<std::string>();
    }
  } else if (config.contains("labels") && config["labels"].is_array()) {
    int idx = 0;
    for (const auto& label : config["labels"]) {
      cfg.labels[idx++] = label.get<std::string>();
    }
  }
  return cfg;
}

} // namespace

Result<std::unique_ptr<Adapter>> create_adapter(const std::string& name) {
  return create_adapter(name, nlohmann::json::object());
}

Result<std::unique_ptr<Adapter>> create_adapter(const std::string& name,
                                                const nlohmann::json& config) {
  if (name == "raw_tensor") {
    return std::unique_ptr<Adapter>(new RawTensorAdapter());
  }
  if (name == "image_classification") {
    auto cfg = parse_classification_config(config);
    if (!cfg) {
      return cfg.error();
    }
    return std::unique_ptr<Adapter>(new ClassificationAdapter(std::move(cfg.value())));
  }
  if (name == "yolo_v8_detection") {
    auto cfg = parse_yolo_config(config);
    if (!cfg) {
      return cfg.error();
    }
    return std::unique_ptr<Adapter>(new YoloV8Adapter(std::move(cfg.value())));
  }
  return Error::make(ErrorCode::ConfigInvalid, "unknown adapter: " + name,
                     "Use raw_tensor, image_classification, or yolo_v8_detection");
}
} // namespace perceptshift::adapters
