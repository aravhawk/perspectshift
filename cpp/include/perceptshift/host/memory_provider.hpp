#pragma once
#include "perceptshift/host/telemetry_snapshot.hpp"
namespace perceptshift::host {
[[nodiscard]] MemorySnapshot read_memory_snapshot();
}
