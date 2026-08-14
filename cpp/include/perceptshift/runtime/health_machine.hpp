#pragma once

#include "perceptshift/runtime/runtime_state.hpp"

#include <string>
#include <vector>

namespace perceptshift::runtime {

struct HealthTransition {
  HealthState from{HealthState::Starting};
  HealthState to{HealthState::Starting};
  std::string reason_code;
};

class HealthMachine {
public:
  [[nodiscard]] HealthState state() const noexcept { return state_; }
  [[nodiscard]] bool control_hold_active() const noexcept { return control_hold_; }
  [[nodiscard]] const std::string& control_hold_reason() const noexcept {
    return control_hold_reason_;
  }
  [[nodiscard]] const std::vector<HealthTransition>& history() const noexcept { return history_; }

  void set_ready(const std::string& reason);
  void set_degraded(const std::string& reason);
  void set_fail_closed(const std::string& reason);
  void begin_recovery(const std::string& reason);
  void set_stopping(const std::string& reason);
  void clear_control_hold();

private:
  void transition(HealthState to, const std::string& reason);

  HealthState state_{HealthState::Starting};
  bool control_hold_{false};
  std::string control_hold_reason_;
  std::vector<HealthTransition> history_;
};

} // namespace perceptshift::runtime
