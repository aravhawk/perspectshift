#include "perceptshift/host/power_provider.hpp"

#include "perceptshift/util/steady_clock.hpp"

#include <fstream>

namespace perceptshift::host {

Result<PowerSnapshot> read_power_snapshot(const PowerProviderConfig& config) {
  PowerSnapshot snap;
  snap.type = config.type;
  snap.timestamp_steady_ns = util::steady_now_ns();

  if (config.type == PowerProviderType::Disabled) {
    snap.status = "unavailable";
    snap.reason_code = "POWER_PROVIDER_DISABLED";
    return Ok(std::move(snap));
  }

#if defined(__linux__)
  if (config.type == PowerProviderType::LinuxIioSysfs) {
    if (config.path.empty()) {
      snap.status = "unavailable";
      snap.reason_code = "POWER_IIO_PATH_MISSING";
      return Ok(std::move(snap));
    }
    std::ifstream in(config.path);
    if (!in) {
      snap.status = "unavailable";
      snap.reason_code = "POWER_IIO_UNREADABLE";
      return Ok(std::move(snap));
    }
    double micro = 0.0;
    if (!(in >> micro)) {
      snap.status = "unavailable";
      snap.reason_code = "POWER_IIO_PARSE_FAILED";
      return Ok(std::move(snap));
    }
    // Common IIO power_*_input is in microwatts.
    snap.power_watts = micro / 1'000'000.0;
    snap.status = "ok";
    snap.reason_code.clear();
    return Ok(std::move(snap));
  }
  if (config.type == PowerProviderType::FileFifo) {
    std::ifstream in(config.path);
    if (!in) {
      snap.status = "unavailable";
      snap.reason_code = "POWER_FIFO_UNREADABLE";
      return Ok(std::move(snap));
    }
    double watts = 0.0;
    if (!(in >> watts)) {
      snap.status = "unavailable";
      snap.reason_code = "POWER_FIFO_PARSE_FAILED";
      return Ok(std::move(snap));
    }
    snap.power_watts = watts;
    snap.status = "ok";
    snap.reason_code.clear();
    return Ok(std::move(snap));
  }
#else
  (void)config;
  snap.status = "unavailable";
  snap.reason_code = "POWER_PROVIDER_LINUX_ONLY";
#endif
  return Ok(std::move(snap));
}

} // namespace perceptshift::host
