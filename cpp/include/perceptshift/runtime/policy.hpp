#pragma once

#include <cstdint>
#include <string>

namespace perceptshift::runtime {

struct RuntimePolicy {
  double deadline_ms{75.0};
  double minimum_dwell_ms{2000.0};
  int promotion_confirmation_frames{30};
  int demotion_confirmation_frames{3};
  int deadline_miss_window_frames{20};
  int deadline_miss_threshold{2};
  int latency_window_samples{256};
  double latency_quantile{0.99};
  double latency_margin_ms{3.0};
  double latency_mad_multiplier{3.0};
  double offline_envelope_weight{1.0};
  double minimum_quality_value{0.0};
  std::string quality_metric_name{"coco_map_50_95"};
  std::string quality_direction{"higher_is_better"};
  bool confidence_escalation_enabled{false};
  double confidence_escalation_threshold{0.35};
  int manual_pin_maximum_seconds{900};
  bool fail_closed_on_stale_input{true};
  bool fail_closed_on_no_eligible_profile{true};
  int recover_confirmation_frames{30};
  double maximum_source_age_ms{150.0};
  int max_transient_failures_before_operator_recovery{5};
};

} // namespace perceptshift::runtime
