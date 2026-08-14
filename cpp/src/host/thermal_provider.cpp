#include "perceptshift/host/thermal_provider.hpp"

#include <filesystem>
#include <fstream>

namespace perceptshift::host {

std::vector<ThermalSample> read_thermal_samples() {
  std::vector<ThermalSample> out;
#if defined(__linux__)
  namespace fs = std::filesystem;
  const fs::path thermal_root{"/sys/class/thermal"};
  std::error_code ec;
  if (!fs::exists(thermal_root, ec)) {
    ThermalSample s;
    s.sensor_id = "none";
    s.provider = "linux_sysfs";
    s.unavailable = Unavailable{"THERMAL_SYSFS_MISSING", "/sys/class/thermal not present"};
    out.push_back(std::move(s));
    return out;
  }
  for (const auto& entry : fs::directory_iterator(thermal_root, ec)) {
    if (!entry.is_directory())
      continue;
    const auto name = entry.path().filename().string();
    if (name.rfind("thermal_zone", 0) != 0)
      continue;
    ThermalSample s;
    s.sensor_id = name;
    s.provider = "linux_sysfs";
    std::ifstream in(entry.path() / "temp");
    long milli = 0;
    if (in >> milli) {
      s.temperature_c = static_cast<double>(milli) / 1000.0;
    } else {
      s.unavailable = Unavailable{"THERMAL_READ_FAILED", "unable to read zone temperature"};
    }
    out.push_back(std::move(s));
  }
  if (out.empty()) {
    ThermalSample s;
    s.sensor_id = "none";
    s.provider = "linux_sysfs";
    s.unavailable = Unavailable{"THERMAL_ZONES_EMPTY", "no thermal zones discovered"};
    out.push_back(std::move(s));
  }
#else
  ThermalSample s;
  s.sensor_id = "none";
  s.provider = "unavailable";
  s.unavailable =
      Unavailable{"THERMAL_PROVIDER_UNSUPPORTED", "Linux sysfs thermal not available on this OS"};
  out.push_back(std::move(s));
#endif
  return out;
}

} // namespace perceptshift::host
