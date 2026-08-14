#pragma once

#include "perceptshift/host/telemetry_snapshot.hpp"

#include <string>

namespace perceptshift::host {

struct HostFingerprint {
  std::string schema_version{"1.0"};
  std::string document_type{"perceptshift.host_fingerprint"};
  std::string created_at_rfc3339;
  std::string architecture;
  std::string os_name;
  std::string os_version;
  std::string hostname_hash;
  TelemetrySnapshot telemetry;
};

[[nodiscard]] HostFingerprint collect_host_fingerprint();
[[nodiscard]] std::string host_fingerprint_to_json(const HostFingerprint& fp);

} // namespace perceptshift::host
