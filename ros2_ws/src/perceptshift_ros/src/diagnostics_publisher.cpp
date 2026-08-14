// Copyright 2026 PerceptShift Authors
// SPDX-License-Identifier: Apache-2.0

#include "perceptshift_ros/diagnostics_publisher.hpp"

#include <diagnostic_msgs/msg/diagnostic_status.hpp>

namespace perceptshift_ros {

DiagnosticsPublisher::DiagnosticsPublisher(rclcpp_lifecycle::LifecycleNode& node)
    : node_(node), updater_(&node) {
  updater_.setHardwareID("perceptshift_runtime");
  updater_.add("runtime", this, &DiagnosticsPublisher::produce);
}

void DiagnosticsPublisher::update(const DiagnosticSnapshot& snapshot) {
  snapshot_ = snapshot;
  updater_.force_update();
}

void DiagnosticsPublisher::force_update() {
  updater_.force_update();
}

void DiagnosticsPublisher::produce(diagnostic_updater::DiagnosticStatusWrapper& status) {
  using diagnostic_msgs::msg::DiagnosticStatus;

  if (snapshot_.internal_health == "ok") {
    status.summary(DiagnosticStatus::OK, "runtime healthy");
  } else if (snapshot_.internal_health == "degraded" || snapshot_.internal_health == "recovering") {
    status.summary(DiagnosticStatus::WARN, snapshot_.internal_health);
  } else {
    status.summary(DiagnosticStatus::ERROR, snapshot_.internal_health);
  }

  status.add("lifecycle_state", snapshot_.lifecycle_state);
  status.add("internal_health", snapshot_.internal_health);
  status.add("active_profile", snapshot_.active_profile);
  status.add("eligible_profiles", static_cast<int>(snapshot_.eligible_profiles));
  status.add("bundle_integrity", snapshot_.bundle_integrity_ok ? "ok" : "failed");
  status.add("input_freshness", snapshot_.input_fresh ? "fresh" : "stale");
  status.add("deadline_misses", static_cast<int>(snapshot_.deadline_misses));
  status.add("inference_failures", static_cast<int>(snapshot_.inference_failures));
  status.add("memory_headroom_bytes", static_cast<double>(snapshot_.available_memory_bytes));
  status.add("temperature_celsius", snapshot_.temperature_valid
                                        ? static_cast<double>(snapshot_.temperature_celsius)
                                        : -1.0);
  status.add("throttling", snapshot_.throttling_valid ? (snapshot_.throttling ? "true" : "false")
                                                      : "unavailable");
  status.add("power_provider", "unavailable");
  status.add("provider_assignment",
             snapshot_.provider_summary.empty() ? "unavailable" : snapshot_.provider_summary);
  status.add("last_successful_inference",
             static_cast<double>(snapshot_.last_successful_sequence_id));
}

} // namespace perceptshift_ros
