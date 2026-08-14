#pragma once

#include "perceptshift/result.hpp"

#include <cstdint>
#include <optional>
#include <string>

namespace perceptshift::host {

enum class PowerProviderType {
  Disabled,
  LinuxIioSysfs,
  FileFifo,
};

struct PowerSnapshot {
  PowerProviderType type{PowerProviderType::Disabled};
  std::optional<double> power_watts;
  std::optional<double> energy_joules;
  std::int64_t timestamp_steady_ns{0};
  std::string status{"unavailable"};
  std::string reason_code{"POWER_PROVIDER_DISABLED"};
};

struct PowerProviderConfig {
  PowerProviderType type{PowerProviderType::Disabled};
  std::string path; // IIO path or FIFO path
};

[[nodiscard]] Result<PowerSnapshot> read_power_snapshot(const PowerProviderConfig& config);

} // namespace perceptshift::host
