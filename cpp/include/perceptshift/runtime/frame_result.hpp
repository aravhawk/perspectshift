#pragma once

#include "perceptshift/adapters/adapter.hpp"
#include "perceptshift/error.hpp"
#include "perceptshift/runtime/runtime_state.hpp"

#include <cstdint>
#include <nlohmann/json.hpp>
#include <optional>
#include <string>

namespace perceptshift::runtime {

struct FrameResult {
  bool ok{false};
  bool control_hold{false};
  std::string control_hold_reason;
  HealthState health_state{HealthState::Starting};
  // Profile that produced this frame's inference output (captured before execute).
  std::string executed_profile_id;
  // Controller active profile after post-frame decision (may differ after a switch).
  std::string next_active_profile_id;
  // Compatibility alias: equals executed_profile_id for this frame's provenance.
  std::string active_profile_id;
  std::optional<SwitchReason> last_switch_reason;
  adapters::NormalizedOutput output;
  double preprocess_ms{0.0};
  double inference_ms{0.0};
  double postprocess_ms{0.0};
  double total_ms{0.0};
  std::string active_provider_summary;
  std::string sample_id;
  std::int64_t sequence_id{0};
  Error error{};
  nlohmann::json telemetry = nlohmann::json::object();
};

} // namespace perceptshift::runtime
