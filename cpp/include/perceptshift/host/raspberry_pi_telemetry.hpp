#pragma once

#include "perceptshift/result.hpp"

#include <cstdint>
#include <optional>
#include <string>

namespace perceptshift::host {

struct RaspberryPiThrottleFlags {
  bool under_voltage_now{false};
  bool freq_capped_now{false};
  bool throttled_now{false};
  bool soft_temp_limit_now{false};
  bool under_voltage_occurred{false};
  bool freq_cap_occurred{false};
  bool throttling_occurred{false};
  bool soft_temp_limit_occurred{false};
  std::uint32_t raw{0};
};

struct RaspberryPiTelemetry {
  bool is_raspberry_pi{false};
  std::string model;
  std::string revision;
  std::optional<double> temperature_c;
  std::optional<RaspberryPiThrottleFlags> throttle;
  std::string status{"unavailable"};
  std::string reason_code;
};

[[nodiscard]] Result<RaspberryPiTelemetry> read_raspberry_pi_telemetry();

} // namespace perceptshift::host
