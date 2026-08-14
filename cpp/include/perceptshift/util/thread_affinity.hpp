#pragma once

#include "perceptshift/result.hpp"

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

namespace perceptshift::util {

struct CpuAffinity {
  std::vector<int> cpu_ids;
};

[[nodiscard]] Result<std::vector<int>> online_cpu_ids();

[[nodiscard]] Result<CpuAffinity> current_affinity();

[[nodiscard]] Result<void> set_affinity(const CpuAffinity& affinity);

[[nodiscard]] Result<void> validate_affinity_subset(const CpuAffinity& requested,
                                                    const std::vector<int>& allowed);

} // namespace perceptshift::util
