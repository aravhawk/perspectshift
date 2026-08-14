#pragma once
#include "perceptshift/host/telemetry_snapshot.hpp"
namespace perceptshift::host {
[[nodiscard]] FrequencySnapshot read_frequency_snapshot();
}
