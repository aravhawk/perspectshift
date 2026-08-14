#include "perceptshift/host/memory_provider.hpp"

#include <fstream>
#include <string>

#if defined(__APPLE__)
#include <mach/mach.h>
#include <sys/sysctl.h>
#endif

namespace perceptshift::host {

MemorySnapshot read_memory_snapshot() {
  MemorySnapshot snap;
#if defined(__linux__)
  std::ifstream in("/proc/meminfo");
  if (!in) {
    snap.unavailable = Unavailable{"MEMINFO_UNAVAILABLE", "unable to open /proc/meminfo"};
    return snap;
  }
  std::string key;
  std::uint64_t value_kb = 0;
  std::string unit;
  while (in >> key >> value_kb >> unit) {
    if (key == "MemTotal:")
      snap.total_bytes = value_kb * 1024ULL;
    if (key == "MemAvailable:")
      snap.available_bytes = value_kb * 1024ULL;
  }
#elif defined(__APPLE__)
  std::uint64_t memsize = 0;
  size_t len = sizeof(memsize);
  if (sysctlbyname("hw.memsize", &memsize, &len, nullptr, 0) == 0) {
    snap.total_bytes = memsize;
  } else {
    snap.unavailable = Unavailable{"SYSCTL_MEM_UNAVAILABLE", "hw.memsize sysctl failed"};
  }
  mach_msg_type_number_t count = HOST_VM_INFO64_COUNT;
  vm_statistics64_data_t vmstat;
  if (host_statistics64(mach_host_self(), HOST_VM_INFO64, reinterpret_cast<host_info64_t>(&vmstat),
                        &count) == KERN_SUCCESS) {
    const std::uint64_t page = static_cast<std::uint64_t>(vm_page_size);
    snap.available_bytes = (static_cast<std::uint64_t>(vmstat.free_count) +
                            static_cast<std::uint64_t>(vmstat.inactive_count)) *
                           page;
  }
#else
  snap.unavailable = Unavailable{"MEMORY_PROVIDER_UNSUPPORTED", "no memory provider for this OS"};
#endif
  return snap;
}

} // namespace perceptshift::host
