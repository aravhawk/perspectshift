#include "perceptshift/util/thread_affinity.hpp"

#include <algorithm>
#include <cstddef>
#include <thread>

#if defined(__linux__)
#include <pthread.h>
#include <sched.h>
#include <unistd.h>
#endif

namespace perceptshift::util {

Result<std::vector<int>> online_cpu_ids() {
  std::vector<int> ids;
#if defined(__linux__)
  const long n = sysconf(_SC_NPROCESSORS_ONLN);
  if (n <= 0) {
    return Err<std::vector<int>>(ErrorCode::TelemetryUnavailable,
                                 "sysconf online CPU count failed");
  }
  const std::size_t count = static_cast<std::size_t>(n);
  ids.reserve(count);
  for (std::size_t i = 0; i < count; ++i) {
    ids.push_back(static_cast<int>(i));
  }
#else
  const unsigned n = std::thread::hardware_concurrency();
  if (n == 0) {
    return Err<std::vector<int>>(ErrorCode::TelemetryUnavailable,
                                 "hardware_concurrency unavailable on this host",
                                 "CPU topology is best-effort outside Linux");
  }
  ids.reserve(static_cast<std::size_t>(n));
  for (unsigned i = 0; i < n; ++i) {
    ids.push_back(static_cast<int>(i));
  }
#endif
  return Ok(std::move(ids));
}

Result<CpuAffinity> current_affinity() {
  CpuAffinity aff;
#if defined(__linux__)
  cpu_set_t set;
  CPU_ZERO(&set);
  if (pthread_getaffinity_np(pthread_self(), sizeof(set), &set) != 0) {
    return Err<CpuAffinity>(ErrorCode::TelemetryUnavailable, "pthread_getaffinity_np failed");
  }
  const long n = sysconf(_SC_NPROCESSORS_CONF);
  if (n <= 0) {
    return Err<CpuAffinity>(ErrorCode::TelemetryUnavailable,
                            "sysconf configured CPU count failed");
  }
  const std::size_t count = static_cast<std::size_t>(n);
  for (std::size_t i = 0; i < count; ++i) {
    if (CPU_ISSET(i, &set) != 0) {
      aff.cpu_ids.push_back(static_cast<int>(i));
    }
  }
#else
  return Err<CpuAffinity>(ErrorCode::TelemetryUnavailable,
                          "thread affinity query unavailable on this OS",
                          "Affinity APIs are supported on Linux");
#endif
  return Ok(std::move(aff));
}

Result<void> set_affinity(const CpuAffinity& affinity) {
#if defined(__linux__)
  if (affinity.cpu_ids.empty()) {
    return Err(ErrorCode::ConfigInvalid, "affinity CPU list is empty");
  }
  cpu_set_t set;
  CPU_ZERO(&set);
  for (int id : affinity.cpu_ids) {
    if (id < 0) {
      return Err(ErrorCode::ConfigInvalid, "negative CPU id in affinity");
    }
    CPU_SET(static_cast<unsigned>(id), &set);
  }
  if (pthread_setaffinity_np(pthread_self(), sizeof(set), &set) != 0) {
    return Err(ErrorCode::ResourceExhausted, "pthread_setaffinity_np failed",
               "Check cpuset permissions and allowed CPU IDs");
  }
  return Ok();
#else
  (void)affinity;
  return Err(ErrorCode::TelemetryUnavailable, "thread affinity set unavailable on this OS",
             "Affinity APIs are supported on Linux");
#endif
}

Result<void> validate_affinity_subset(const CpuAffinity& requested,
                                      const std::vector<int>& allowed) {
  for (int id : requested.cpu_ids) {
    if (std::find(allowed.begin(), allowed.end(), id) == allowed.end()) {
      return Err(ErrorCode::ConfigInvalid, "requested CPU id outside allowed set");
    }
  }
  return Ok();
}

} // namespace perceptshift::util
