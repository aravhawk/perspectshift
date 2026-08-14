#pragma once

#include "perceptshift/result.hpp"

#include <cstdint>
#include <string>
#include <vector>

namespace perceptshift::host {

struct CpuCore {
  int logical_id{-1};
  int package_id{-1};
  int core_id{-1};
  int cluster_id{-1};
  std::vector<int> thread_siblings;
  int capacity{-1};
};

struct CpuTopology {
  std::vector<int> online_cpus;
  std::vector<int> isolated_cpus;
  std::vector<CpuCore> cores;
  std::string unavailable_reason;
};

[[nodiscard]] Result<CpuTopology> read_cpu_topology();

} // namespace perceptshift::host
