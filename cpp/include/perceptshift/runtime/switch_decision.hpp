#pragma once

#include "perceptshift/runtime/runtime_state.hpp"

#include <optional>
#include <string>

namespace perceptshift::runtime {

struct SwitchDecision {
  bool should_switch{false};
  std::optional<std::string> from_profile_id;
  std::optional<std::string> to_profile_id;
  SwitchReason reason{SwitchReason::StartupSelect};
  std::string evidence;
};

} // namespace perceptshift::runtime
