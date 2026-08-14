#pragma once

#include <cstdint>
#include <mutex>
#include <optional>
#include <string>
#include <vector>

namespace perceptshift::runtime {

struct FrameEnvelope {
  std::int64_t source_timestamp_ns{0};
  std::int64_t receive_steady_ns{0};
  std::uint64_t sequence{0};
  std::vector<std::uint8_t> payload;
  std::size_t width{0};
  std::size_t height{0};
  std::size_t stride_bytes{0};
  std::string pixel_format{"rgb8"};
};

// Capacity must be 1 for latest_only policy.
class LatestFrameQueue {
public:
  explicit LatestFrameQueue(std::size_t capacity = 1);

  // Returns true if a prior unread frame was overwritten.
  bool push(FrameEnvelope frame);
  std::optional<FrameEnvelope> pop_latest();
  [[nodiscard]] std::uint64_t dropped_count() const;
  [[nodiscard]] std::size_t size() const;

private:
  mutable std::mutex mu_;
  std::size_t capacity_;
  std::optional<FrameEnvelope> slot_;
  std::uint64_t dropped_{0};
};

} // namespace perceptshift::runtime
