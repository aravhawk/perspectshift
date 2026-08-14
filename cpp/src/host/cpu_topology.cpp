#include "perceptshift/host/cpu_topology.hpp"

#include "perceptshift/util/thread_affinity.hpp"

#include <filesystem>
#include <fstream>
#include <optional>
#include <sstream>

namespace perceptshift::host {
namespace {

#if defined(__linux__)
std::optional<int> read_int_file(const std::filesystem::path& path) {
  std::ifstream in(path);
  if (!in) {
    return std::nullopt;
  }
  int v = 0;
  in >> v;
  if (!in) {
    return std::nullopt;
  }
  return v;
}

std::vector<int> parse_cpu_list(const std::string& text) {
  std::vector<int> out;
  std::stringstream ss(text);
  std::string token;
  while (std::getline(ss, token, ',')) {
    if (token.empty()) {
      continue;
    }
    const auto dash = token.find('-');
    if (dash == std::string::npos) {
      out.push_back(std::stoi(token));
    } else {
      const int a = std::stoi(token.substr(0, dash));
      const int b = std::stoi(token.substr(dash + 1));
      for (int i = a; i <= b; ++i) {
        out.push_back(i);
      }
    }
  }
  return out;
}
#endif

} // namespace

Result<CpuTopology> read_cpu_topology() {
  CpuTopology topo;
  auto online = util::online_cpu_ids();
  if (!online) {
    return Err<CpuTopology>(online.error());
  }
  topo.online_cpus = online.value();

#if defined(__linux__)
  for (int id : topo.online_cpus) {
    CpuCore core;
    core.logical_id = id;
    const auto base = std::filesystem::path("/sys/devices/system/cpu/cpu" + std::to_string(id));
    if (auto v = read_int_file(base / "topology/physical_package_id")) {
      core.package_id = *v;
    }
    if (auto v = read_int_file(base / "topology/core_id")) {
      core.core_id = *v;
    }
    if (auto v = read_int_file(base / "topology/cluster_id")) {
      core.cluster_id = *v;
    }
    if (auto v = read_int_file(base / "cpu_capacity")) {
      core.capacity = *v;
    }
    std::ifstream sib(base / "topology/thread_siblings_list");
    if (sib) {
      std::string line;
      std::getline(sib, line);
      core.thread_siblings = parse_cpu_list(line);
    }
    topo.cores.push_back(std::move(core));
  }
  std::ifstream iso("/sys/devices/system/cpu/isolated");
  if (iso) {
    std::string line;
    std::getline(iso, line);
    topo.isolated_cpus = parse_cpu_list(line);
  }
#else
  for (int id : topo.online_cpus) {
    CpuCore core;
    core.logical_id = id;
    topo.cores.push_back(core);
  }
  topo.unavailable_reason = "LINUX_SYSFS_TOPOLOGY_UNAVAILABLE";
#endif
  return Ok(std::move(topo));
}

} // namespace perceptshift::host
