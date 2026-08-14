#pragma once
#include "perceptshift/host/telemetry_snapshot.hpp"

#include <vector>
namespace perceptshift::host {
[[nodiscard]] std::vector<ThermalSample> read_thermal_samples();
}
