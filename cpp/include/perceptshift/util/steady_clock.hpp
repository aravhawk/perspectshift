#pragma once

#include <chrono>
#include <cstdint>

namespace perceptshift::util {

using SteadyClock = std::chrono::steady_clock;
using SteadyTimePoint = SteadyClock::time_point;

[[nodiscard]] inline std::int64_t steady_now_ns() noexcept {
  return std::chrono::duration_cast<std::chrono::nanoseconds>(SteadyClock::now().time_since_epoch())
      .count();
}

[[nodiscard]] inline std::int64_t duration_ns(SteadyTimePoint start, SteadyTimePoint end) noexcept {
  return std::chrono::duration_cast<std::chrono::nanoseconds>(end - start).count();
}

} // namespace perceptshift::util
