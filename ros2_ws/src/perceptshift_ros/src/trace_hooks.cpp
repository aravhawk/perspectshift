// Copyright 2026 PerceptShift Authors
// SPDX-License-Identifier: Apache-2.0

#include "perceptshift_ros/trace_hooks.hpp"

#include <rclcpp/rclcpp.hpp>

namespace perceptshift_ros {

namespace {
rclcpp::Logger logger() {
  return rclcpp::get_logger("perceptshift_ros.trace");
}
} // namespace

void TraceHooks::frame_received(uint64_t sequence_id) {
  if (!enabled_) {
    return;
  }
  RCLCPP_DEBUG(logger(), "trace.frame_received seq=%llu",
               static_cast<unsigned long long>(sequence_id));
}

void TraceHooks::frame_queued(uint64_t sequence_id) {
  if (!enabled_) {
    return;
  }
  RCLCPP_DEBUG(logger(), "trace.frame_queued seq=%llu",
               static_cast<unsigned long long>(sequence_id));
}

void TraceHooks::frame_dropped(uint64_t sequence_id, const std::string& reason) {
  if (!enabled_) {
    return;
  }
  RCLCPP_DEBUG(logger(), "trace.frame_dropped seq=%llu reason=%s",
               static_cast<unsigned long long>(sequence_id), reason.c_str());
}

void TraceHooks::decision_start(uint64_t sequence_id) {
  if (!enabled_) {
    return;
  }
  RCLCPP_DEBUG(logger(), "trace.decision_start seq=%llu",
               static_cast<unsigned long long>(sequence_id));
}

void TraceHooks::decision_end(uint64_t sequence_id, const std::string& profile_id) {
  if (!enabled_) {
    return;
  }
  RCLCPP_DEBUG(logger(), "trace.decision_end seq=%llu profile=%s",
               static_cast<unsigned long long>(sequence_id), profile_id.c_str());
}

void TraceHooks::profile_selected(const std::string& profile_id) {
  if (!enabled_) {
    return;
  }
  RCLCPP_DEBUG(logger(), "trace.profile_selected profile=%s", profile_id.c_str());
}

void TraceHooks::preprocess_start(uint64_t sequence_id) {
  if (!enabled_) {
    return;
  }
  RCLCPP_DEBUG(logger(), "trace.preprocess_start seq=%llu",
               static_cast<unsigned long long>(sequence_id));
}

void TraceHooks::preprocess_end(uint64_t sequence_id) {
  if (!enabled_) {
    return;
  }
  RCLCPP_DEBUG(logger(), "trace.preprocess_end seq=%llu",
               static_cast<unsigned long long>(sequence_id));
}

void TraceHooks::inference_start(uint64_t sequence_id) {
  if (!enabled_) {
    return;
  }
  RCLCPP_DEBUG(logger(), "trace.inference_start seq=%llu",
               static_cast<unsigned long long>(sequence_id));
}

void TraceHooks::inference_end(uint64_t sequence_id) {
  if (!enabled_) {
    return;
  }
  RCLCPP_DEBUG(logger(), "trace.inference_end seq=%llu",
               static_cast<unsigned long long>(sequence_id));
}

void TraceHooks::postprocess_start(uint64_t sequence_id) {
  if (!enabled_) {
    return;
  }
  RCLCPP_DEBUG(logger(), "trace.postprocess_start seq=%llu",
               static_cast<unsigned long long>(sequence_id));
}

void TraceHooks::postprocess_end(uint64_t sequence_id) {
  if (!enabled_) {
    return;
  }
  RCLCPP_DEBUG(logger(), "trace.postprocess_end seq=%llu",
               static_cast<unsigned long long>(sequence_id));
}

void TraceHooks::result_publish(uint64_t sequence_id) {
  if (!enabled_) {
    return;
  }
  RCLCPP_DEBUG(logger(), "trace.result_publish seq=%llu",
               static_cast<unsigned long long>(sequence_id));
}

void TraceHooks::deadline_miss(uint64_t sequence_id) {
  if (!enabled_) {
    return;
  }
  RCLCPP_DEBUG(logger(), "trace.deadline_miss seq=%llu",
               static_cast<unsigned long long>(sequence_id));
}

void TraceHooks::health_transition(const std::string& from, const std::string& to) {
  if (!enabled_) {
    return;
  }
  RCLCPP_DEBUG(logger(), "trace.health_transition from=%s to=%s", from.c_str(), to.c_str());
}

void TraceHooks::profile_switch(const std::string& from, const std::string& to) {
  if (!enabled_) {
    return;
  }
  RCLCPP_DEBUG(logger(), "trace.profile_switch from=%s to=%s", from.c_str(), to.c_str());
}

void TraceHooks::control_hold_request(bool active, const std::string& reason) {
  if (!enabled_) {
    return;
  }
  RCLCPP_DEBUG(logger(), "trace.control_hold_request active=%d reason=%s", active ? 1 : 0,
               reason.c_str());
}

} // namespace perceptshift_ros
