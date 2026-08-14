#include "perceptshift/runtime/health_machine.hpp"

namespace perceptshift::runtime {

void HealthMachine::transition(HealthState to, const std::string& reason) {
  if (state_ == to) {
    return;
  }
  history_.push_back(HealthTransition{state_, to, reason});
  state_ = to;
}

void HealthMachine::set_ready(const std::string& reason) {
  control_hold_ = false;
  control_hold_reason_.clear();
  transition(HealthState::Ready, reason);
}

void HealthMachine::set_degraded(const std::string& reason) {
  transition(HealthState::Degraded, reason);
}

void HealthMachine::set_fail_closed(const std::string& reason) {
  control_hold_ = true;
  control_hold_reason_ = reason;
  transition(HealthState::FailClosed, reason);
}

void HealthMachine::begin_recovery(const std::string& reason) {
  transition(HealthState::Recovering, reason);
}

void HealthMachine::set_stopping(const std::string& reason) {
  transition(HealthState::Stopping, reason);
}

void HealthMachine::clear_control_hold() {
  control_hold_ = false;
  control_hold_reason_.clear();
}

} // namespace perceptshift::runtime
