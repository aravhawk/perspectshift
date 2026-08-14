#pragma once

#include <string>

namespace perceptshift::runtime {

enum class HealthState {
  Starting,
  Ready,
  Degraded,
  FailClosed,
  Recovering,
  Stopping,
};

[[nodiscard]] inline const char* to_string(HealthState s) noexcept {
  switch (s) {
  case HealthState::Starting:
    return "starting";
  case HealthState::Ready:
    return "ready";
  case HealthState::Degraded:
    return "degraded";
  case HealthState::FailClosed:
    return "fail_closed";
  case HealthState::Recovering:
    return "recovering";
  case HealthState::Stopping:
    return "stopping";
  }
  return "unknown";
}

enum class SwitchReason {
  StartupSelect,
  DeadlineRiskDemotion,
  QualityPromotion,
  ConfidenceEscalation,
  ManualPin,
  PinExpired,
  ProfileUnhealthy,
  Recovery,
  NoEligible,
};

[[nodiscard]] inline const char* to_string(SwitchReason r) noexcept {
  switch (r) {
  case SwitchReason::StartupSelect:
    return "startup_select";
  case SwitchReason::DeadlineRiskDemotion:
    return "deadline_risk_demotion";
  case SwitchReason::QualityPromotion:
    return "quality_promotion";
  case SwitchReason::ConfidenceEscalation:
    return "confidence_escalation";
  case SwitchReason::ManualPin:
    return "manual_pin";
  case SwitchReason::PinExpired:
    return "pin_expired";
  case SwitchReason::ProfileUnhealthy:
    return "profile_unhealthy";
  case SwitchReason::Recovery:
    return "recovery";
  case SwitchReason::NoEligible:
    return "no_eligible";
  }
  return "unknown";
}

} // namespace perceptshift::runtime
