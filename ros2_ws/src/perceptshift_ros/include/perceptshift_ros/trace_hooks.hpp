// Copyright 2026 PerceptShift Authors
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <cstdint>
#include <string>

namespace perceptshift_ros {

/**
 * Optional low-overhead trace hooks for LTTng/ros2_tracing when available.
 * When tracing is disabled these calls are no-ops.
 */
class TraceHooks {
public:
  void set_enabled(bool enabled) { enabled_ = enabled; }
  bool enabled() const { return enabled_; }

  void frame_received(uint64_t sequence_id);
  void frame_queued(uint64_t sequence_id);
  void frame_dropped(uint64_t sequence_id, const std::string& reason);
  void decision_start(uint64_t sequence_id);
  void decision_end(uint64_t sequence_id, const std::string& profile_id);
  void profile_selected(const std::string& profile_id);
  void preprocess_start(uint64_t sequence_id);
  void preprocess_end(uint64_t sequence_id);
  void inference_start(uint64_t sequence_id);
  void inference_end(uint64_t sequence_id);
  void postprocess_start(uint64_t sequence_id);
  void postprocess_end(uint64_t sequence_id);
  void result_publish(uint64_t sequence_id);
  void deadline_miss(uint64_t sequence_id);
  void health_transition(const std::string& from, const std::string& to);
  void profile_switch(const std::string& from, const std::string& to);
  void control_hold_request(bool active, const std::string& reason);

private:
  bool enabled_{false};
};

} // namespace perceptshift_ros
