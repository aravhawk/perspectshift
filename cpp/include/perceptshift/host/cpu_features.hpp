#pragma once

#include <string>
#include <vector>

namespace perceptshift::host {

struct CpuFeatures {
  std::string architecture;
  bool asimd{false};
  bool fp{false};
  bool aes{false};
  bool crc32{false};
  bool atomics{false};
  bool fp16{false};
  bool dotprod{false};
  bool sve{false};
  bool sve2{false};
  bool i8mm{false};
  bool bf16{false};
  bool sme{false};
  bool sme2{false};
  std::vector<std::string> unavailable_reason_codes;
};

[[nodiscard]] CpuFeatures detect_cpu_features();

} // namespace perceptshift::host
