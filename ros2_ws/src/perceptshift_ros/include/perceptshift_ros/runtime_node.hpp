// Copyright 2026 PerceptShift Authors
// SPDX-License-Identifier: Apache-2.0

#pragma once

#include "perceptshift_ros/diagnostics_publisher.hpp"
#include "perceptshift_ros/image_intake.hpp"
#include "perceptshift_ros/trace_hooks.hpp"

#include <atomic>
#include <chrono>
#include <condition_variable>
#include <diagnostic_updater/diagnostic_updater.hpp>
#include <memory>
#include <mutex>
#include <optional>
#include <perceptshift/host/telemetry_snapshot.hpp>
#include <perceptshift/runtime/runtime_engine.hpp>
#include <perceptshift_msgs/msg/classification_array.hpp>
#include <perceptshift_msgs/msg/control_hold_request.hpp>
#include <perceptshift_msgs/msg/detection_array.hpp>
#include <perceptshift_msgs/msg/inference_trace.hpp>
#include <perceptshift_msgs/msg/profile_state.hpp>
#include <perceptshift_msgs/msg/runtime_health.hpp>
#include <perceptshift_msgs/msg/switch_event.hpp>
#include <perceptshift_msgs/srv/clear_profile_pin.hpp>
#include <perceptshift_msgs/srv/get_runtime_status.hpp>
#include <perceptshift_msgs/srv/pin_profile.hpp>
#include <perceptshift_msgs/srv/request_recovery.hpp>
#include <perceptshift_msgs/srv/update_runtime_policy.hpp>
#include <rclcpp/rclcpp.hpp>
#include <rclcpp_lifecycle/lifecycle_node.hpp>
#include <sensor_msgs/msg/image.hpp>
#include <string>
#include <thread>

namespace perceptshift_ros {

struct QueuedFrame {
  uint64_t sequence_id{0};
  std::int64_t receive_steady_ns{0};
  sensor_msgs::msg::Image::ConstSharedPtr image;
};
struct RuntimeParameters {
  std::string bundle_path;
  std::string image_topic{"/camera/image_raw"};
  std::string task{"yolo_v8_detection"};
  double deadline_ms{75.0};
  bool enable_mutation_services{false};
  bool require_signature{false};
  bool allow_symlinked_model_files{false};
  int queue_capacity{1};
  std::string queue_policy{"latest_only"};
  double maximum_source_age_ms{150.0};
  int telemetry_period_ms{500};
};

/**
 * Lifecycle component that transports ROS I/O and runs inference through the
 * shared native RuntimeEngine (same engine used by perceptshift-runtime CLI).
 */
class RuntimeNode : public rclcpp_lifecycle::LifecycleNode {
public:
  explicit RuntimeNode(const rclcpp::NodeOptions& options = rclcpp::NodeOptions());

  rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn
  on_configure(const rclcpp_lifecycle::State& previous_state) override;
  rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn
  on_activate(const rclcpp_lifecycle::State& previous_state) override;
  rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn
  on_deactivate(const rclcpp_lifecycle::State& previous_state) override;
  rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn
  on_cleanup(const rclcpp_lifecycle::State& previous_state) override;
  rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn
  on_shutdown(const rclcpp_lifecycle::State& previous_state) override;
  rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn
  on_error(const rclcpp_lifecycle::State& previous_state) override;

  const RuntimeParameters& parameters() const { return params_; }

private:
  void declare_parameters();
  bool load_parameters();
  void create_publishers();
  void create_services();
  void create_subscription();
  void publish_control_hold(bool active, const std::string& reason_code,
                            const std::string& summary);
  void publish_health();
  void on_image(const sensor_msgs::msg::Image::ConstSharedPtr msg);
  void on_telemetry_timer();
  void worker_loop();
  void publish_frame_result(const perceptshift::runtime::FrameResult& result,
                            const sensor_msgs::msg::Image& source);
  void publish_profile_states();
  void publish_switch_event(const perceptshift::runtime::FrameResult& result, uint64_t sequence_id);
  void publish_inference_trace(const perceptshift::runtime::FrameResult& result,
                               const perceptshift::runtime::FrameRequest& request);

  void handle_get_status(
      const std::shared_ptr<perceptshift_msgs::srv::GetRuntimeStatus::Request> request,
      std::shared_ptr<perceptshift_msgs::srv::GetRuntimeStatus::Response> response);
  void
  handle_pin_profile(const std::shared_ptr<perceptshift_msgs::srv::PinProfile::Request> request,
                     std::shared_ptr<perceptshift_msgs::srv::PinProfile::Response> response);
  void
  handle_clear_pin(const std::shared_ptr<perceptshift_msgs::srv::ClearProfilePin::Request> request,
                   std::shared_ptr<perceptshift_msgs::srv::ClearProfilePin::Response> response);
  void handle_update_policy(
      const std::shared_ptr<perceptshift_msgs::srv::UpdateRuntimePolicy::Request> request,
      std::shared_ptr<perceptshift_msgs::srv::UpdateRuntimePolicy::Response> response);
  void
  handle_recovery(const std::shared_ptr<perceptshift_msgs::srv::RequestRecovery::Request> request,
                  std::shared_ptr<perceptshift_msgs::srv::RequestRecovery::Response> response);

  RuntimeParameters params_;
  ImageIntake image_intake_;
  TraceHooks traces_;
  std::unique_ptr<DiagnosticsPublisher> diagnostics_;

  rclcpp::CallbackGroup::SharedPtr image_cb_group_;
  rclcpp::CallbackGroup::SharedPtr service_cb_group_;
  rclcpp::CallbackGroup::SharedPtr telemetry_cb_group_;

  rclcpp::Subscription<sensor_msgs::msg::Image>::SharedPtr image_sub_;
  rclcpp_lifecycle::LifecyclePublisher<perceptshift_msgs::msg::ClassificationArray>::SharedPtr
      class_pub_;
  rclcpp_lifecycle::LifecyclePublisher<perceptshift_msgs::msg::DetectionArray>::SharedPtr det_pub_;
  rclcpp_lifecycle::LifecyclePublisher<perceptshift_msgs::msg::RuntimeHealth>::SharedPtr
      health_pub_;
  rclcpp_lifecycle::LifecyclePublisher<perceptshift_msgs::msg::ProfileState>::SharedPtr
      profile_pub_;
  rclcpp_lifecycle::LifecyclePublisher<perceptshift_msgs::msg::InferenceTrace>::SharedPtr
      trace_pub_;
  rclcpp_lifecycle::LifecyclePublisher<perceptshift_msgs::msg::SwitchEvent>::SharedPtr switch_pub_;
  rclcpp_lifecycle::LifecyclePublisher<perceptshift_msgs::msg::ControlHoldRequest>::SharedPtr
      hold_pub_;

  rclcpp::Service<perceptshift_msgs::srv::GetRuntimeStatus>::SharedPtr status_srv_;
  rclcpp::Service<perceptshift_msgs::srv::PinProfile>::SharedPtr pin_srv_;
  rclcpp::Service<perceptshift_msgs::srv::ClearProfilePin>::SharedPtr clear_pin_srv_;
  rclcpp::Service<perceptshift_msgs::srv::UpdateRuntimePolicy>::SharedPtr policy_srv_;
  rclcpp::Service<perceptshift_msgs::srv::RequestRecovery>::SharedPtr recovery_srv_;

  rclcpp::TimerBase::SharedPtr telemetry_timer_;

  std::unique_ptr<perceptshift::runtime::RuntimeEngine> engine_;
  std::thread worker_thread_;
  std::atomic<bool> worker_stop_{false};
  std::mutex frame_mutex_;
  std::optional<QueuedFrame> latest_queued_;
  std::condition_variable frame_cv_;
  std::atomic<uint64_t> dropped_frames_{0};
  bool last_source_stale_{false};

  std::mutex state_mutex_;
  std::string active_profile_id_;
  std::string bundle_id_;
  std::string policy_hash_;
  uint8_t health_state_{perceptshift_msgs::msg::RuntimeHealth::HEALTH_UNKNOWN};
  std::string health_reason_{"unconfigured"};
  bool control_hold_requested_{true};
  bool core_configured_{false};
  std::atomic<uint64_t> sequence_id_{0};
  std::atomic<uint64_t> last_successful_sequence_id_{0};
  std::atomic<uint32_t> consecutive_failures_{0};
  std::atomic<uint32_t> consecutive_deadline_misses_{0};
  std::atomic<bool> accepting_frames_{false};
};

} // namespace perceptshift_ros
