#include "perceptshift/runtime/latest_frame_queue.hpp"

namespace perceptshift::runtime {

LatestFrameQueue::LatestFrameQueue(std::size_t capacity) : capacity_(capacity == 0 ? 1 : capacity) {
}

bool LatestFrameQueue::push(FrameEnvelope frame) {
  std::lock_guard lock(mu_);
  const bool dropped = slot_.has_value();
  if (dropped) {
    ++dropped_;
  }
  slot_ = std::move(frame);
  return dropped;
}

std::optional<FrameEnvelope> LatestFrameQueue::pop_latest() {
  std::lock_guard lock(mu_);
  auto out = std::move(slot_);
  slot_.reset();
  return out;
}

std::uint64_t LatestFrameQueue::dropped_count() const {
  std::lock_guard lock(mu_);
  return dropped_;
}

std::size_t LatestFrameQueue::size() const {
  std::lock_guard lock(mu_);
  return slot_ ? 1U : 0U;
}

} // namespace perceptshift::runtime
