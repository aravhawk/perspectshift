#include "perceptshift/host/host_fingerprint.hpp"

#include "perceptshift/crypto/digest.hpp"

#include <chrono>
#include <ctime>
#include <sstream>

#if defined(__linux__) || defined(__APPLE__)
#include <sys/utsname.h>
#endif

namespace perceptshift::host {
namespace {

std::string utc_now_rfc3339() {
  using clock = std::chrono::system_clock;
  const auto now = clock::now();
  const std::time_t t = clock::to_time_t(now);
  std::tm tm{};
  gmtime_r(&t, &tm);
  char buf[64];
  std::strftime(buf, sizeof(buf), "%Y-%m-%dT%H:%M:%SZ", &tm);
  return buf;
}

} // namespace

HostFingerprint collect_host_fingerprint() {
  HostFingerprint fp;
  fp.created_at_rfc3339 = utc_now_rfc3339();
  fp.telemetry = collect_telemetry_snapshot();
  fp.architecture = fp.telemetry.cpu.architecture;
#if defined(__linux__) || defined(__APPLE__)
  utsname u{};
  if (uname(&u) == 0) {
    fp.os_name = u.sysname;
    fp.os_version = std::string(u.release) + " " + u.version;
    auto hash = crypto::sha256_bytes(std::string_view(u.nodename));
    if (hash) {
      fp.hostname_hash = crypto::to_hex(hash.value());
    }
  }
#endif
  return fp;
}

std::string host_fingerprint_to_json(const HostFingerprint& fp) {
  std::ostringstream oss;
  oss << "{"
      << "\"schema_version\":\"" << fp.schema_version << "\","
      << "\"document_type\":\"" << fp.document_type << "\","
      << "\"created_at\":\"" << fp.created_at_rfc3339 << "\","
      << "\"architecture\":\"" << fp.architecture << "\","
      << "\"os\":{\"name\":\"" << fp.os_name << "\",\"version\":\"" << fp.os_version << "\"},"
      << "\"hostname_hash\":\"" << fp.hostname_hash << "\""
      << "}";
  return oss.str();
}

} // namespace perceptshift::host
