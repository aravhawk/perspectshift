#include "perceptshift/host/frequency_provider.hpp"

#include <fstream>

namespace perceptshift::host {

FrequencySnapshot read_frequency_snapshot() {
  FrequencySnapshot snap;
#if defined(__linux__)
  {
    std::ifstream in("/sys/devices/system/cpu/cpu0/cpufreq/scaling_governor");
    std::string g;
    if (in >> g)
      snap.governor = g;
  }
  {
    std::ifstream in("/sys/devices/system/cpu/cpu0/cpufreq/scaling_driver");
    std::string d;
    if (in >> d)
      snap.driver = d;
  }
  {
    std::ifstream in("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq");
    std::uint64_t khz = 0;
    if (in >> khz)
      snap.current_khz = khz;
  }
  if (!snap.governor && !snap.current_khz) {
    snap.unavailable = Unavailable{"CPUFREQ_UNAVAILABLE", "cpufreq sysfs not readable"};
  }
#else
  snap.unavailable = Unavailable{"CPUFREQ_UNSUPPORTED", "cpufreq sysfs not available on this OS"};
#endif
  return snap;
}

} // namespace perceptshift::host
