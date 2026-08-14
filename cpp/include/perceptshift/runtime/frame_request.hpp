#pragma once

#include <cstdint>
#include <string>
#include <vector>

namespace perceptshift::runtime {

enum class FrameInputKind {
  TensorBytes,
  RawImageBytes,
  ZerosSmoke,
};

struct FrameRequest {
  std::int64_t sequence_id{0};
  std::string sample_id;
  std::string trace_id;
  std::int64_t source_timestamp_ns{0};
  std::int64_t receive_steady_ns{0};
  FrameInputKind kind{FrameInputKind::TensorBytes};
  std::vector<std::uint8_t> payload;
  std::size_t width{0};
  std::size_t height{0};
  std::size_t stride_bytes{0};
  std::string pixel_format{"rgb8"};
  bool source_stale{false};
  float confidence_hint{-1.f};
};

} // namespace perceptshift::runtime
