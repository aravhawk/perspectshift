#include "perceptshift/host/telemetry_snapshot.hpp"

#include "perceptshift/host/frequency_provider.hpp"
#include "perceptshift/host/memory_provider.hpp"
#include "perceptshift/host/thermal_provider.hpp"
namespace perceptshift::host {
TelemetrySnapshot collect_telemetry_snapshot() {
  TelemetrySnapshot snap;
  snap.cpu = detect_cpu_features();
  snap.memory = read_memory_snapshot();
  snap.frequency = read_frequency_snapshot();
  snap.thermal = read_thermal_samples();
  snap.power_unavailable =
      Unavailable{"POWER_PROVIDER_DISABLED", "no real power sensor configured"};
  return snap;
}
} // namespace perceptshift::host
