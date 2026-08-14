#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace perceptshift::profiles {

enum class ProfileStatus { Certified, Rejected, Draft };

struct Profile {
  std::string profile_id;
  std::string label;
  std::string model_sha256;
  std::string model_relative_path;
  ProfileStatus status{ProfileStatus::Draft};
  double certified_quality{0.0};
  double certified_p99_ms{0.0};
  double offline_envelope_ms{0.0};
  double utility{0.0}; // higher preferred when latency allows
  std::int64_t peak_rss_bytes{0};
  std::vector<std::string> required_cpu_features;
  bool warmed{false};
  bool healthy{true};
  int failure_count{0};
  std::int64_t cooldown_until_steady_ns{0};
};

} // namespace perceptshift::profiles
