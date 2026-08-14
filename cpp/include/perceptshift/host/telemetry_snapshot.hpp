#pragma once

#include "perceptshift/host/cpu_features.hpp"

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

namespace perceptshift::host {

struct Unavailable {
  std::string reason_code;
  std::string message;
};

struct MemorySnapshot {
  std::optional<std::uint64_t> total_bytes;
  std::optional<std::uint64_t> available_bytes;
  std::optional<std::uint64_t> cgroup_limit_bytes;
  std::optional<Unavailable> unavailable;
};

struct ThermalSample {
  std::string sensor_id;
  std::string provider;
  std::optional<double> temperature_c;
  std::optional<Unavailable> unavailable;
};

struct FrequencySnapshot {
  std::optional<std::string> governor;
  std::optional<std::string> driver;
  std::optional<std::uint64_t> current_khz;
  std::optional<Unavailable> unavailable;
};

struct TelemetrySnapshot {
  CpuFeatures cpu;
  MemorySnapshot memory;
  FrequencySnapshot frequency;
  std::vector<ThermalSample> thermal;
  std::optional<Unavailable> power_unavailable;
};

[[nodiscard]] TelemetrySnapshot collect_telemetry_snapshot();

} // namespace perceptshift::host
