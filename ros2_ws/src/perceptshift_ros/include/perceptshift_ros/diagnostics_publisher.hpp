// Copyright 2026 PerceptShift Authors
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include <diagnostic_msgs/msg/diagnostic_array.hpp>
#include <diagnostic_updater/diagnostic_updater.hpp>
#include <rclcpp_lifecycle/lifecycle_node.hpp>
#include <string>

namespace perceptshift_ros {

struct DiagnosticSnapshot {
  std::string lifecycle_state{"unknown"};
  std::string internal_health{"unknown"};
  std::string active_profile;
  uint32_t eligible_profiles{0};
  bool bundle_integrity_ok{false};
  bool input_fresh{false};
  uint32_t deadline_misses{0};
  uint32_t inference_failures{0};
  uint64_t available_memory_bytes{0};
  bool temperature_valid{false};
  float temperature_celsius{0.0F};
  bool throttling_valid{false};
  bool throttling{false};
  std::string provider_summary;
  uint64_t last_successful_sequence_id{0};
};

/**
 * Publishes diagnostic_msgs/DiagnosticArray with stable hardware IDs and keys.
 */
class DiagnosticsPublisher {
public:
  explicit DiagnosticsPublisher(rclcpp_lifecycle::LifecycleNode& node);

  void update(const DiagnosticSnapshot& snapshot);
  void force_update();

private:
  void produce(diagnostic_updater::DiagnosticStatusWrapper& status);

  rclcpp_lifecycle::LifecycleNode& node_;
  diagnostic_updater::Updater updater_;
  DiagnosticSnapshot snapshot_;
};

} // namespace perceptshift_ros
