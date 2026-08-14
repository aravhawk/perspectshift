#include "perceptshift/runtime/policy_loader.hpp"

#include "perceptshift/crypto/digest.hpp"

#include <fstream>
namespace perceptshift::runtime {
namespace {

void apply_field(RuntimePolicy& policy, const nlohmann::json& j) {
  if (!j.is_object()) {
    return;
  }
  if (j.contains("deadline_ms") && j["deadline_ms"].is_number()) {
    policy.deadline_ms = j["deadline_ms"].get<double>();
  }
  if (j.contains("minimum_dwell_ms") && j["minimum_dwell_ms"].is_number()) {
    policy.minimum_dwell_ms = j["minimum_dwell_ms"].get<double>();
  }
  if (j.contains("promotion_confirmation_frames") &&
      j["promotion_confirmation_frames"].is_number_integer()) {
    policy.promotion_confirmation_frames = j["promotion_confirmation_frames"].get<int>();
  }
  if (j.contains("demotion_confirmation_frames") &&
      j["demotion_confirmation_frames"].is_number_integer()) {
    policy.demotion_confirmation_frames = j["demotion_confirmation_frames"].get<int>();
  }
  if (j.contains("deadline_miss_window_frames") &&
      j["deadline_miss_window_frames"].is_number_integer()) {
    policy.deadline_miss_window_frames = j["deadline_miss_window_frames"].get<int>();
  }
  if (j.contains("deadline_miss_threshold") && j["deadline_miss_threshold"].is_number_integer()) {
    policy.deadline_miss_threshold = j["deadline_miss_threshold"].get<int>();
  }
  if (j.contains("latency_window_samples") && j["latency_window_samples"].is_number_integer()) {
    policy.latency_window_samples = j["latency_window_samples"].get<int>();
  }
  if (j.contains("latency_quantile") && j["latency_quantile"].is_number()) {
    policy.latency_quantile = j["latency_quantile"].get<double>();
  }
  if (j.contains("latency_margin_ms") && j["latency_margin_ms"].is_number()) {
    policy.latency_margin_ms = j["latency_margin_ms"].get<double>();
  }
  if (j.contains("latency_mad_multiplier") && j["latency_mad_multiplier"].is_number()) {
    policy.latency_mad_multiplier = j["latency_mad_multiplier"].get<double>();
  }
  if (j.contains("offline_envelope_weight") && j["offline_envelope_weight"].is_number()) {
    policy.offline_envelope_weight = j["offline_envelope_weight"].get<double>();
  }
  if (j.contains("minimum_quality_value") && j["minimum_quality_value"].is_number()) {
    policy.minimum_quality_value = j["minimum_quality_value"].get<double>();
  }
  if (j.contains("quality_metric_name") && j["quality_metric_name"].is_string()) {
    policy.quality_metric_name = j["quality_metric_name"].get<std::string>();
  }
  if (j.contains("quality_direction") && j["quality_direction"].is_string()) {
    policy.quality_direction = j["quality_direction"].get<std::string>();
  }
  if (j.contains("confidence_escalation_enabled") &&
      j["confidence_escalation_enabled"].is_boolean()) {
    policy.confidence_escalation_enabled = j["confidence_escalation_enabled"].get<bool>();
  }
  if (j.contains("confidence_escalation_threshold") &&
      j["confidence_escalation_threshold"].is_number()) {
    policy.confidence_escalation_threshold = j["confidence_escalation_threshold"].get<double>();
  }
  if (j.contains("manual_pin_maximum_seconds") &&
      j["manual_pin_maximum_seconds"].is_number_integer()) {
    policy.manual_pin_maximum_seconds = j["manual_pin_maximum_seconds"].get<int>();
  }
  if (j.contains("fail_closed_on_stale_input") && j["fail_closed_on_stale_input"].is_boolean()) {
    policy.fail_closed_on_stale_input = j["fail_closed_on_stale_input"].get<bool>();
  }
  if (j.contains("fail_closed_on_no_eligible_profile") &&
      j["fail_closed_on_no_eligible_profile"].is_boolean()) {
    policy.fail_closed_on_no_eligible_profile = j["fail_closed_on_no_eligible_profile"].get<bool>();
  }
  if (j.contains("recover_confirmation_frames") &&
      j["recover_confirmation_frames"].is_number_integer()) {
    policy.recover_confirmation_frames = j["recover_confirmation_frames"].get<int>();
  }
  if (j.contains("maximum_source_age_ms") && j["maximum_source_age_ms"].is_number()) {
    policy.maximum_source_age_ms = j["maximum_source_age_ms"].get<double>();
  }
}

} // namespace

RuntimePolicy default_runtime_policy() {
  return RuntimePolicy{};
}

Result<RuntimePolicy> load_runtime_policy_json(const nlohmann::json& document) {
  RuntimePolicy policy = default_runtime_policy();
  const nlohmann::json* src = &document;
  if (document.is_object() && document.contains("runtime_policy") &&
      document["runtime_policy"].is_object()) {
    src = &document["runtime_policy"];
  } else if (document.is_object() && document.contains("policy") &&
             document["policy"].is_object()) {
    src = &document["policy"];
  }
  if (!src->is_object()) {
    return Error::make(ErrorCode::ConfigInvalid, "runtime policy document must be a JSON object");
  }
  apply_field(policy, *src);
  if (policy.deadline_ms <= 0.0) {
    return Error::make(ErrorCode::ConfigInvalid, "deadline_ms must be positive");
  }
  if (policy.demotion_confirmation_frames < 1 || policy.promotion_confirmation_frames < 1) {
    return Error::make(ErrorCode::ConfigInvalid, "confirmation frame counts must be >= 1");
  }
  return policy;
}

Result<RuntimePolicy> load_runtime_policy_file(const std::filesystem::path& path) {
  std::ifstream in(path);
  if (!in) {
    return Error::make(ErrorCode::ConfigInvalid, "unable to open policy file: " + path.string());
  }
  try {
    nlohmann::json j;
    in >> j;
    return load_runtime_policy_json(j);
  } catch (const std::exception& ex) {
    return Error::make(ErrorCode::ConfigInvalid,
                       std::string("malformed policy JSON: ") + ex.what());
  }
}

RuntimePolicy merge_runtime_policy(RuntimePolicy base, const nlohmann::json& overlay) {
  apply_field(base, overlay);
  return base;
}

nlohmann::json runtime_policy_to_json(const RuntimePolicy& policy) {
  return nlohmann::json{
      {"deadline_ms", policy.deadline_ms},
      {"minimum_dwell_ms", policy.minimum_dwell_ms},
      {"promotion_confirmation_frames", policy.promotion_confirmation_frames},
      {"demotion_confirmation_frames", policy.demotion_confirmation_frames},
      {"deadline_miss_window_frames", policy.deadline_miss_window_frames},
      {"deadline_miss_threshold", policy.deadline_miss_threshold},
      {"latency_window_samples", policy.latency_window_samples},
      {"latency_quantile", policy.latency_quantile},
      {"latency_margin_ms", policy.latency_margin_ms},
      {"latency_mad_multiplier", policy.latency_mad_multiplier},
      {"offline_envelope_weight", policy.offline_envelope_weight},
      {"minimum_quality_value", policy.minimum_quality_value},
      {"quality_metric_name", policy.quality_metric_name},
      {"quality_direction", policy.quality_direction},
      {"confidence_escalation_enabled", policy.confidence_escalation_enabled},
      {"confidence_escalation_threshold", policy.confidence_escalation_threshold},
      {"manual_pin_maximum_seconds", policy.manual_pin_maximum_seconds},
      {"fail_closed_on_stale_input", policy.fail_closed_on_stale_input},
      {"fail_closed_on_no_eligible_profile", policy.fail_closed_on_no_eligible_profile},
      {"recover_confirmation_frames", policy.recover_confirmation_frames},
      {"maximum_source_age_ms", policy.maximum_source_age_ms},
      {"max_transient_failures_before_operator_recovery",
       policy.max_transient_failures_before_operator_recovery},
  };
}

Result<RuntimePolicy> validate_runtime_policy(const RuntimePolicy& policy) {
  if (policy.deadline_ms <= 0.0) {
    return Error::make(ErrorCode::ConfigInvalid, "deadline_ms must be positive");
  }
  if (policy.demotion_confirmation_frames < 1 || policy.promotion_confirmation_frames < 1) {
    return Error::make(ErrorCode::ConfigInvalid, "confirmation frame counts must be >= 1");
  }
  if (policy.max_transient_failures_before_operator_recovery < 1) {
    return Error::make(ErrorCode::ConfigInvalid,
                       "max_transient_failures_before_operator_recovery must be >= 1");
  }
  return policy;
}

std::string runtime_policy_hash(const RuntimePolicy& policy) {
  const auto canonical = runtime_policy_to_json(policy).dump();
  auto digest = crypto::sha256_bytes(canonical);
  if (!digest) {
    return {};
  }
  return crypto::to_hex(digest.value());
}

} // namespace perceptshift::runtime
