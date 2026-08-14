// Copyright 2026 PerceptShift Authors
// SPDX-License-Identifier: Apache-2.0

#include "perceptshift_ros/runtime_node.hpp"

#include <chrono>
#include <filesystem>
#include <fstream>
#include <sstream>
#include <perceptshift/host/raspberry_pi_telemetry.hpp>
#include <perceptshift/host/telemetry_snapshot.hpp>
#include <perceptshift/runtime/eligibility.hpp>
#include <perceptshift/runtime/policy_loader.hpp>
#include <perceptshift/runtime/runtime_engine.hpp>
#include <rclcpp/qos.hpp>
#include <rclcpp_components/register_node_macro.hpp>

namespace perceptshift_ros {

RuntimeNode::RuntimeNode(const rclcpp::NodeOptions& options)
    : rclcpp_lifecycle::LifecycleNode("perceptshift_runtime", options) {
  declare_parameters();
  image_cb_group_ = create_callback_group(rclcpp::CallbackGroupType::MutuallyExclusive);
  service_cb_group_ = create_callback_group(rclcpp::CallbackGroupType::MutuallyExclusive);
  telemetry_cb_group_ = create_callback_group(rclcpp::CallbackGroupType::MutuallyExclusive);
}

void RuntimeNode::declare_parameters() {
  declare_parameter<std::string>("bundle_path", "");
  declare_parameter<std::string>("image_topic", "/camera/image_raw");
  declare_parameter<std::string>("task", "yolo_v8_detection");
  declare_parameter<double>("deadline_ms", 75.0);
  declare_parameter<bool>("enable_mutation_services", false);
  declare_parameter<bool>("require_signature", false);
  declare_parameter<bool>("allow_symlinked_model_files", false);
  declare_parameter<int>("queue_capacity", 1);
  declare_parameter<std::string>("queue_policy", "latest_only");
  declare_parameter<double>("maximum_source_age_ms", 150.0);
  declare_parameter<int>("telemetry_period_ms", 500);
  declare_parameter<bool>("enable_tracing", false);
}

bool RuntimeNode::load_parameters() {
  params_.bundle_path = get_parameter("bundle_path").as_string();
  params_.image_topic = get_parameter("image_topic").as_string();
  params_.task = get_parameter("task").as_string();
  params_.deadline_ms = get_parameter("deadline_ms").as_double();
  params_.enable_mutation_services = get_parameter("enable_mutation_services").as_bool();
  params_.require_signature = get_parameter("require_signature").as_bool();
  params_.allow_symlinked_model_files = get_parameter("allow_symlinked_model_files").as_bool();
  params_.queue_capacity = get_parameter("queue_capacity").as_int();
  params_.queue_policy = get_parameter("queue_policy").as_string();
  params_.maximum_source_age_ms = get_parameter("maximum_source_age_ms").as_double();
  params_.telemetry_period_ms = get_parameter("telemetry_period_ms").as_int();
  traces_.set_enabled(get_parameter("enable_tracing").as_bool());

  if (params_.bundle_path.empty()) {
    RCLCPP_ERROR(get_logger(),
                 "bundle_path is required and must point to a user-supplied profile bundle");
    return false;
  }
  if (!std::filesystem::exists(params_.bundle_path)) {
    RCLCPP_ERROR(get_logger(), "bundle_path does not exist: %s", params_.bundle_path.c_str());
    return false;
  }
  if (params_.deadline_ms <= 0.0) {
    RCLCPP_ERROR(get_logger(), "deadline_ms must be positive");
    return false;
  }
  if (params_.queue_policy != "latest_only") {
    RCLCPP_ERROR(get_logger(), "unsupported queue_policy: %s", params_.queue_policy.c_str());
    return false;
  }
  image_intake_.set_capacity(params_.queue_capacity);
  return true;
}

void RuntimeNode::create_publishers() {
  auto reliable = rclcpp::QoS(rclcpp::KeepLast(10)).reliable().transient_local();
  auto best_effort = rclcpp::QoS(rclcpp::KeepLast(20)).best_effort();

  class_pub_ =
      create_publisher<perceptshift_msgs::msg::ClassificationArray>("~/classifications", reliable);
  det_pub_ = create_publisher<perceptshift_msgs::msg::DetectionArray>("~/detections", reliable);
  health_pub_ = create_publisher<perceptshift_msgs::msg::RuntimeHealth>("~/health", reliable);
  profile_pub_ = create_publisher<perceptshift_msgs::msg::ProfileState>("~/profiles", reliable);
  trace_pub_ = create_publisher<perceptshift_msgs::msg::InferenceTrace>("~/traces", best_effort);
  switch_pub_ = create_publisher<perceptshift_msgs::msg::SwitchEvent>("~/switches", reliable);
  hold_pub_ = create_publisher<perceptshift_msgs::msg::ControlHoldRequest>("~/control_hold_request",
                                                                           reliable);
}

void RuntimeNode::create_services() {
  const rclcpp::QoS service_qos{rclcpp::ServicesQoS()};

  status_srv_ = create_service<perceptshift_msgs::srv::GetRuntimeStatus>(
      "~/get_runtime_status",
      std::bind(&RuntimeNode::handle_get_status, this, std::placeholders::_1,
                std::placeholders::_2),
      service_qos, service_cb_group_);

  if (!params_.enable_mutation_services) {
    RCLCPP_WARN(get_logger(), "mutation services disabled; enable_mutation_services:=true required "
                              "for pin/policy/recovery");
    return;
  }

  pin_srv_ = create_service<perceptshift_msgs::srv::PinProfile>(
      "~/pin_profile",
      std::bind(&RuntimeNode::handle_pin_profile, this, std::placeholders::_1,
                std::placeholders::_2),
      service_qos, service_cb_group_);
  clear_pin_srv_ = create_service<perceptshift_msgs::srv::ClearProfilePin>(
      "~/clear_profile_pin",
      std::bind(&RuntimeNode::handle_clear_pin, this, std::placeholders::_1, std::placeholders::_2),
      service_qos, service_cb_group_);
  policy_srv_ = create_service<perceptshift_msgs::srv::UpdateRuntimePolicy>(
      "~/update_runtime_policy",
      std::bind(&RuntimeNode::handle_update_policy, this, std::placeholders::_1,
                std::placeholders::_2),
      service_qos, service_cb_group_);
  recovery_srv_ = create_service<perceptshift_msgs::srv::RequestRecovery>(
      "~/request_recovery",
      std::bind(&RuntimeNode::handle_recovery, this, std::placeholders::_1, std::placeholders::_2),
      service_qos, service_cb_group_);
}

void RuntimeNode::create_subscription() {
  rclcpp::SubscriptionOptions opts;
  opts.callback_group = image_cb_group_;
  // Jazzy lifecycle create_subscription expects rclcpp::QoS depth overload + options.
  image_sub_ = rclcpp_lifecycle::LifecycleNode::create_subscription<sensor_msgs::msg::Image>(
      params_.image_topic, rclcpp::SensorDataQoS(),
      [this](const sensor_msgs::msg::Image::ConstSharedPtr msg) { on_image(msg); }, opts);
}

rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn
RuntimeNode::on_configure(const rclcpp_lifecycle::State&) {
  RCLCPP_INFO(get_logger(), "on_configure: loading parameters and RuntimeEngine");
  if (!load_parameters()) {
    return rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn::FAILURE;
  }

  create_publishers();
  create_services();
  diagnostics_ = std::make_unique<DiagnosticsPublisher>(*this);

  perceptshift::runtime::RuntimeEngineConfig cfg;
  cfg.bundle_path = params_.bundle_path;
  cfg.signature_policy = params_.require_signature
                             ? perceptshift::bundle::SignaturePolicy::Required
                             : perceptshift::bundle::SignaturePolicy::Optional;
  cfg.strict_inventory = true;
  cfg.allow_symlinks = params_.allow_symlinked_model_files;
  cfg.allow_zeros_smoke = false;

  engine_ = std::make_unique<perceptshift::runtime::RuntimeEngine>();
  RCLCPP_INFO(get_logger(), "on_configure: RuntimeEngine::configure bundle=%s",
              params_.bundle_path.c_str());
  auto configured = engine_->configure(cfg);
  if (!configured) {
    RCLCPP_ERROR(get_logger(), "RuntimeEngine configure failed: %s",
                 configured.error().message.c_str());
    core_configured_ = false;
    health_state_ = perceptshift_msgs::msg::RuntimeHealth::HEALTH_FAIL_CLOSED;
    health_reason_ = perceptshift::to_string(configured.error().code);
    control_hold_requested_ = true;
    publish_control_hold(true, health_reason_, "configure failed; control-hold request");
    engine_.reset();
    return rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn::FAILURE;
  }

  // Apply ROS-declared deadline/age policy before warmup eligibility selection.
  {
    auto pol = engine_->policy();
    pol.deadline_ms = params_.deadline_ms;
    pol.maximum_source_age_ms = params_.maximum_source_age_ms;
    auto updated = engine_->update_policy(pol);
    if (!updated) {
      RCLCPP_ERROR(get_logger(), "RuntimeEngine policy update failed: %s",
                   updated.error().message.c_str());
      core_configured_ = false;
      health_state_ = perceptshift_msgs::msg::RuntimeHealth::HEALTH_FAIL_CLOSED;
      health_reason_ = perceptshift::to_string(updated.error().code);
      control_hold_requested_ = true;
      publish_control_hold(true, health_reason_, "policy update failed; control-hold request");
      engine_.reset();
      return rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn::FAILURE;
    }
  }

  RCLCPP_INFO(get_logger(), "on_configure: load_and_warmup");
  auto warmed = engine_->load_and_warmup();
  if (!warmed) {
    RCLCPP_ERROR(get_logger(), "RuntimeEngine warmup failed: %s", warmed.error().message.c_str());
    core_configured_ = false;
    health_state_ = perceptshift_msgs::msg::RuntimeHealth::HEALTH_FAIL_CLOSED;
    health_reason_ = perceptshift::to_string(warmed.error().code);
    control_hold_requested_ = true;
    publish_control_hold(true, health_reason_, "warmup failed; control-hold request");
    engine_.reset();
    return rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn::FAILURE;
  }

  const auto st = engine_->status_json();
  core_configured_ = true;
  control_hold_requested_ = engine_->control_hold_active();
  health_state_ = control_hold_requested_
                      ? perceptshift_msgs::msg::RuntimeHealth::HEALTH_FAIL_CLOSED
                      : perceptshift_msgs::msg::RuntimeHealth::HEALTH_OK;
  health_reason_ = control_hold_requested_ ? "control_hold" : "core_configured";
  active_profile_id_ = st.value("active_profile_id", "");
  bundle_id_ = st.value("bundle_id", params_.bundle_path);
  policy_hash_ = "engine_policy";

  publish_control_hold(control_hold_requested_, health_reason_, "configured with RuntimeEngine");
  RCLCPP_INFO(get_logger(), "on_configure: RuntimeEngine ready profile=%s",
              active_profile_id_.c_str());
  return rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn::SUCCESS;
}

rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn
RuntimeNode::on_activate(const rclcpp_lifecycle::State&) {
  class_pub_->on_activate();
  det_pub_->on_activate();
  health_pub_->on_activate();
  profile_pub_->on_activate();
  trace_pub_->on_activate();
  switch_pub_->on_activate();
  hold_pub_->on_activate();

  create_subscription();
  accepting_frames_.store(true);
  worker_stop_.store(false);
  if (engine_ && !worker_thread_.joinable()) {
    worker_thread_ = std::thread(&RuntimeNode::worker_loop, this);
  }

  telemetry_timer_ =
      create_wall_timer(std::chrono::milliseconds(params_.telemetry_period_ms),
                        std::bind(&RuntimeNode::on_telemetry_timer, this), telemetry_cb_group_);

  publish_health();
  publish_control_hold(control_hold_requested_, health_reason_, "activated");
  return rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn::SUCCESS;
}

rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn
RuntimeNode::on_deactivate(const rclcpp_lifecycle::State&) {
  accepting_frames_.store(false);
  worker_stop_.store(true);
  frame_cv_.notify_all();
  if (worker_thread_.joinable()) {
    worker_thread_.join();
  }
  image_sub_.reset();
  telemetry_timer_.reset();
  (void)image_intake_.take_latest();
  {
    std::lock_guard<std::mutex> lock(frame_mutex_);
    latest_queued_.reset();
  }

  class_pub_->on_deactivate();
  det_pub_->on_deactivate();
  health_pub_->on_deactivate();
  profile_pub_->on_deactivate();
  trace_pub_->on_deactivate();
  switch_pub_->on_deactivate();
  hold_pub_->on_deactivate();
  return rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn::SUCCESS;
}

rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn
RuntimeNode::on_cleanup(const rclcpp_lifecycle::State&) {
  accepting_frames_.store(false);
  worker_stop_.store(true);
  frame_cv_.notify_all();
  if (worker_thread_.joinable()) {
    worker_thread_.join();
  }
  image_sub_.reset();
  telemetry_timer_.reset();
  status_srv_.reset();
  pin_srv_.reset();
  clear_pin_srv_.reset();
  policy_srv_.reset();
  recovery_srv_.reset();
  class_pub_.reset();
  det_pub_.reset();
  health_pub_.reset();
  profile_pub_.reset();
  trace_pub_.reset();
  switch_pub_.reset();
  hold_pub_.reset();
  diagnostics_.reset();
  engine_.reset();
  core_configured_ = false;
  health_state_ = perceptshift_msgs::msg::RuntimeHealth::HEALTH_UNKNOWN;
  health_reason_ = "cleaned";
  return rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn::SUCCESS;
}

rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn
RuntimeNode::on_shutdown(const rclcpp_lifecycle::State&) {
  accepting_frames_.store(false);
  if (hold_pub_ && hold_pub_->is_activated()) {
    publish_control_hold(true, "shutdown", "runtime shutting down; control-hold requested");
  }
  telemetry_timer_.reset();
  image_sub_.reset();
  return rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn::SUCCESS;
}

rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn
RuntimeNode::on_error(const rclcpp_lifecycle::State&) {
  accepting_frames_.store(false);
  health_state_ = perceptshift_msgs::msg::RuntimeHealth::HEALTH_ERROR;
  health_reason_ = "lifecycle_error";
  control_hold_requested_ = true;
  publish_control_hold(true, health_reason_, "lifecycle error; control-hold requested");
  if (diagnostics_) {
    DiagnosticSnapshot snap;
    snap.lifecycle_state = "error";
    snap.internal_health = "error";
    snap.active_profile = active_profile_id_;
    diagnostics_->update(snap);
  }
  return rclcpp_lifecycle::node_interfaces::LifecycleNodeInterface::CallbackReturn::SUCCESS;
}

void RuntimeNode::publish_control_hold(bool active, const std::string& reason_code,
                                       const std::string& summary) {
  if (!hold_pub_) {
    return;
  }
  perceptshift_msgs::msg::ControlHoldRequest msg;
  msg.header.stamp = now();
  msg.request_active = active;
  msg.reason_code = reason_code;
  msg.trace_id = "";
  msg.health_state = health_state_;
  msg.first_active_timestamp = now();
  msg.sequence_id = sequence_id_.load();
  msg.summary = summary;
  control_hold_requested_ = active;
  traces_.control_hold_request(active, reason_code);
  if (hold_pub_->is_activated()) {
    hold_pub_->publish(msg);
  }
}

void RuntimeNode::publish_health() {
  if (!health_pub_ || !health_pub_->is_activated()) {
    return;
  }
  perceptshift_msgs::msg::RuntimeHealth msg;
  msg.header.stamp = now();
  msg.health_state = health_state_;
  msg.reason_code = health_reason_;
  msg.summary = health_reason_;
  msg.active_profile_id = active_profile_id_;
  std::uint32_t eligible = 0;
  if (engine_ && engine_->controller()) {
    const auto now_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
                            std::chrono::steady_clock::now().time_since_epoch())
                            .count();
    for (auto* p : engine_->registry().all()) {
      double bound = p->offline_envelope_ms;
      const auto el = perceptshift::runtime::evaluate_eligibility(
          *p, engine_->policy(), bound, now_ns, false);
      if (el.eligible) {
        ++eligible;
      }
    }
  }
  msg.eligible_profile_count = eligible;
  msg.source_stale = last_source_stale_;
  msg.control_hold_requested = control_hold_requested_;

  auto telemetry = perceptshift::host::collect_telemetry_snapshot();
  if (telemetry.memory.available_bytes.has_value()) {
    msg.available_memory_bytes = *telemetry.memory.available_bytes;
  } else {
    msg.available_memory_bytes = 0;
  }
  // Process RSS from /proc when available; never invent a meaningful zero.
  msg.process_rss_bytes = 0;
#if defined(__linux__)
  std::ifstream status("/proc/self/status");
  std::string line;
  while (std::getline(status, line)) {
    if (line.rfind("VmRSS:", 0) == 0) {
      std::istringstream iss(line.substr(6));
      std::uint64_t kb = 0;
      iss >> kb;
      msg.process_rss_bytes = kb * 1024ULL;
      break;
    }
  }
#endif
  msg.primary_temperature_valid = false;
  msg.primary_temperature_celsius = 0.0F;
  for (const auto& sample : telemetry.thermal) {
    if (sample.temperature_c.has_value()) {
      msg.primary_temperature_celsius = static_cast<float>(*sample.temperature_c);
      msg.primary_temperature_valid = true;
      break;
    }
  }
  auto pi = perceptshift::host::read_raspberry_pi_telemetry();
  msg.throttling_valid = false;
  msg.throttling = false;
  if (pi && pi.value().throttle.has_value()) {
    msg.throttling_valid = true;
    msg.throttling = pi.value().throttle->throttled_now;
  }

  msg.consecutive_inference_failures = consecutive_failures_.load();
  msg.consecutive_deadline_misses = consecutive_deadline_misses_.load();
  msg.last_successful_sequence_id = last_successful_sequence_id_.load();
  health_pub_->publish(msg);

  if (diagnostics_) {
    DiagnosticSnapshot snap;
    snap.lifecycle_state = get_current_state().label();
    snap.internal_health = control_hold_requested_ ? "fail_closed" : "ok";
    snap.active_profile = active_profile_id_;
    snap.eligible_profiles = msg.eligible_profile_count;
    snap.bundle_integrity_ok = core_configured_;
    snap.input_fresh = accepting_frames_.load() && !last_source_stale_;
    snap.deadline_misses = consecutive_deadline_misses_.load();
    snap.inference_failures = consecutive_failures_.load();
    snap.last_successful_sequence_id = last_successful_sequence_id_.load();
    diagnostics_->update(snap);
  }
}

void RuntimeNode::on_image(const sensor_msgs::msg::Image::ConstSharedPtr msg) {
  if (!accepting_frames_.load() || !msg) {
    return;
  }
  const auto seq = sequence_id_.fetch_add(1) + 1;
  traces_.frame_received(seq);

  const auto validated = image_intake_.validate(*msg);
  if (!validated.ok) {
    traces_.frame_dropped(seq, validated.reason_code);
    consecutive_failures_.fetch_add(1);
    return;
  }

  QueuedFrame queued;
  queued.sequence_id = seq;
  queued.receive_steady_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
                                 std::chrono::steady_clock::now().time_since_epoch())
                                 .count();
  queued.image = msg;
  {
    std::lock_guard<std::mutex> lock(frame_mutex_);
    if (latest_queued_) {
      dropped_frames_.fetch_add(1);
    }
    latest_queued_ = std::move(queued);
  }
  frame_cv_.notify_one();
  traces_.frame_queued(seq);
}

void RuntimeNode::worker_loop() {
  while (!worker_stop_.load()) {
    QueuedFrame queued;
    {
      std::unique_lock<std::mutex> lock(frame_mutex_);
      frame_cv_.wait_for(lock, std::chrono::milliseconds(50), [this] {
        return worker_stop_.load() || latest_queued_.has_value();
      });
      if (worker_stop_.load()) {
        break;
      }
      if (!latest_queued_) {
        continue;
      }
      queued = std::move(*latest_queued_);
      latest_queued_.reset();
    }
    if (!queued.image || !engine_ || !engine_->ready()) {
      continue;
    }
    const auto seq = queued.sequence_id;
    traces_.decision_start(seq);
    const auto& frame = *queued.image;
    perceptshift::runtime::FrameRequest req;
    req.sequence_id = static_cast<std::int64_t>(seq);
    req.sample_id = frame.header.frame_id;
    req.source_timestamp_ns = static_cast<std::int64_t>(frame.header.stamp.sec) * 1'000'000'000LL +
                              static_cast<std::int64_t>(frame.header.stamp.nanosec);
    req.receive_steady_ns = queued.receive_steady_ns;
    req.kind = perceptshift::runtime::FrameInputKind::RawImageBytes;
    req.payload.assign(frame.data.begin(), frame.data.end());
    req.width = frame.width;
    req.height = frame.height;
    req.stride_bytes = frame.step;
    req.pixel_format = frame.encoding;

    // Source age uses ROS clock domain (supports sim time); never compare to steady clock.
    const auto max_age_ms = engine_->policy().maximum_source_age_ms;
    if (req.source_timestamp_ns == 0) {
      req.source_stale = true;
    } else if (max_age_ms > 0.0) {
      const auto ros_now = now();
      const std::int64_t ros_now_ns =
          static_cast<std::int64_t>(ros_now.seconds()) * 1'000'000'000LL +
          static_cast<std::int64_t>(ros_now.nanoseconds() % 1'000'000'000LL);
      const double age_ms =
          static_cast<double>(ros_now_ns - req.source_timestamp_ns) / 1.0e6;
      req.source_stale = age_ms > max_age_ms;
    }
    last_source_stale_ = req.source_stale;

    auto result = engine_->execute_frame(req);
    if (!result) {
      consecutive_failures_.fetch_add(1);
      continue;
    }
    traces_.decision_end(seq, result.value().active_profile_id);
    // Deadline-miss accounting from actual FrameResult timing.
    const double deadline_ms = engine_->policy().deadline_ms;
    const bool missed = result.value().total_ms > deadline_ms;
    if (missed) {
      consecutive_deadline_misses_.fetch_add(1);
    } else if (result.value().ok) {
      consecutive_deadline_misses_.store(0);
    }
    publish_frame_result(result.value(), frame);
    publish_inference_trace(result.value(), req);
    if (result.value().last_switch_reason.has_value()) {
      publish_switch_event(result.value(), seq);
    }
    publish_profile_states();
    {
      std::lock_guard<std::mutex> lock(state_mutex_);
      if (result.value().ok) {
        last_successful_sequence_id_.store(seq);
        consecutive_failures_.store(0);
        active_profile_id_ = result.value().active_profile_id;
        control_hold_requested_ = result.value().control_hold;
        health_state_ = control_hold_requested_
                            ? perceptshift_msgs::msg::RuntimeHealth::HEALTH_FAIL_CLOSED
                            : perceptshift_msgs::msg::RuntimeHealth::HEALTH_OK;
        health_reason_ = control_hold_requested_ ? "control_hold" : "ok";
      } else {
        consecutive_failures_.fetch_add(1);
        if (result.value().control_hold) {
          control_hold_requested_ = true;
          health_state_ = perceptshift_msgs::msg::RuntimeHealth::HEALTH_FAIL_CLOSED;
          health_reason_ = result.value().control_hold_reason.empty()
                               ? result.value().error.message
                               : result.value().control_hold_reason;
        }
      }
    }
    if (!result.value().ok && result.value().control_hold) {
      publish_control_hold(true,
                           result.value().control_hold_reason.empty()
                               ? result.value().error.message
                               : result.value().control_hold_reason,
                           "control-hold request: no eligible profile");
    }
    traces_.result_publish(seq);
  }
}

void RuntimeNode::publish_frame_result(const perceptshift::runtime::FrameResult& result,
                                       const sensor_msgs::msg::Image& source) {
  if (result.output.task.find("class") != std::string::npos ||
      !result.output.classifications.empty()) {
    if (class_pub_ && class_pub_->is_activated()) {
      perceptshift_msgs::msg::ClassificationArray msg;
      msg.header = source.header;
      msg.header.stamp = now();
      msg.profile_id = result.executed_profile_id.empty() ? result.active_profile_id
                                                          : result.executed_profile_id;
      msg.sequence_id = static_cast<uint64_t>(result.sequence_id);
      msg.source_width = source.width;
      msg.source_height = source.height;
      msg.adapter_confidence = result.output.confidence_signal;
      msg.confidence_valid = result.output.confidence_signal >= 0.f;
      for (const auto& c : result.output.classifications) {
        perceptshift_msgs::msg::Classification item;
        item.class_id = c.class_id;
        item.score = c.score;
        item.label = c.label;
        msg.predictions.push_back(item);
      }
      class_pub_->publish(msg);
    }
  }
  if (!result.output.detections.empty() || result.output.task.find("detect") != std::string::npos ||
      result.output.task.find("yolo") != std::string::npos) {
    if (det_pub_ && det_pub_->is_activated()) {
      perceptshift_msgs::msg::DetectionArray msg;
      msg.header = source.header;
      msg.header.stamp = now();
      msg.profile_id = result.executed_profile_id.empty() ? result.active_profile_id
                                                          : result.executed_profile_id;
      msg.sequence_id = static_cast<uint64_t>(result.sequence_id);
      msg.source_width = source.width;
      msg.source_height = source.height;
      msg.adapter_confidence = result.output.confidence_signal;
      msg.confidence_valid = result.output.confidence_signal >= 0.f;
      for (const auto& d : result.output.detections) {
        perceptshift_msgs::msg::Detection item;
        item.class_id = d.class_id;
        item.score = d.score;
        item.label = d.label;
        item.x_min = d.x;
        item.y_min = d.y;
        item.x_max = d.x + d.w;
        item.y_max = d.y + d.h;
        // Detection.{x,y,w,h} is top-left + size (converted from YOLO center format).
        msg.detections.push_back(item);
      }
      det_pub_->publish(msg);
    }
  }
}

void RuntimeNode::on_telemetry_timer() {
  publish_health();
}

void RuntimeNode::handle_get_status(
    const std::shared_ptr<perceptshift_msgs::srv::GetRuntimeStatus::Request>,
    std::shared_ptr<perceptshift_msgs::srv::GetRuntimeStatus::Response> response) {
  std::lock_guard<std::mutex> lock(state_mutex_);
  response->success = true;
  response->active_profile_id = active_profile_id_;
  response->bundle_id = bundle_id_;
  response->policy_summary = "deadline_aware_soft_realtime";
  response->policy_hash = policy_hash_;
  response->health.header.stamp = now();
  response->health.health_state = health_state_;
  response->health.reason_code = health_reason_;
  response->health.summary = health_reason_;
  response->health.active_profile_id = active_profile_id_;
  response->health.control_hold_requested = control_hold_requested_;
  std::uint32_t eligible = 0;
  if (engine_ && engine_->controller()) {
    const auto now_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
                            std::chrono::steady_clock::now().time_since_epoch())
                            .count();
    for (auto* p : engine_->registry().all()) {
      double bound = p->offline_envelope_ms;
      const auto el = perceptshift::runtime::evaluate_eligibility(
          *p, engine_->policy(), bound, now_ns, false);
      if (el.eligible) {
        ++eligible;
      }
    }
  }
  response->health.eligible_profile_count = eligible;
  response->health.consecutive_deadline_misses = consecutive_deadline_misses_.load();
  response->error_code.clear();
  response->error_message.clear();
}

void RuntimeNode::handle_pin_profile(
    const std::shared_ptr<perceptshift_msgs::srv::PinProfile::Request> request,
    std::shared_ptr<perceptshift_msgs::srv::PinProfile::Response> response) {
  if (request->profile_id.empty() || request->duration_seconds == 0) {
    response->accepted = false;
    response->error_code = "invalid_request";
    response->error_message = "profile_id and duration_seconds are required";
    return;
  }
  if (!engine_ || !engine_->controller()) {
    response->accepted = false;
    response->error_code = "no_eligible_profile";
    response->error_message = "cannot pin without a configured RuntimeEngine";
    return;
  }
  const auto now_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
                          std::chrono::steady_clock::now().time_since_epoch())
                          .count();
  const bool ok = engine_->controller()->request_pin(request->profile_id, now_ns,
                                                     static_cast<int>(request->duration_seconds));
  response->accepted = ok;
  if (!ok) {
    response->error_code = "pin_rejected";
    response->error_message = "controller rejected pin request";
    return;
  }
  response->expiry = now() + rclcpp::Duration::from_seconds(request->duration_seconds);
  active_profile_id_ = request->profile_id;
}

void RuntimeNode::handle_clear_pin(
    const std::shared_ptr<perceptshift_msgs::srv::ClearProfilePin::Request>,
    std::shared_ptr<perceptshift_msgs::srv::ClearProfilePin::Response> response) {
  if (engine_ && engine_->controller()) {
    engine_->controller()->clear_pin();
  }
  response->success = true;
  response->error_code.clear();
  response->error_message.clear();
}

void RuntimeNode::handle_update_policy(
    const std::shared_ptr<perceptshift_msgs::srv::UpdateRuntimePolicy::Request> request,
    std::shared_ptr<perceptshift_msgs::srv::UpdateRuntimePolicy::Response> response) {
  if (!engine_ || !engine_->controller()) {
    response->accepted = false;
    response->error_code = "engine_not_ready";
    response->error_message = "RuntimeEngine not configured";
    response->previous_policy_hash = policy_hash_;
    response->effective_policy_hash = policy_hash_;
    return;
  }
  const std::string previous = engine_->controller()->policy_hash();
  auto next = engine_->policy();
  if (request->apply_deadline) {
    if (request->deadline_ms <= 0.0) {
      response->accepted = false;
      response->error_code = "invalid_deadline";
      response->error_message = "deadline_ms must be positive";
      response->previous_policy_hash = previous;
      response->effective_policy_hash = previous;
      return;
    }
    next.deadline_ms = request->deadline_ms;
    params_.deadline_ms = request->deadline_ms;
  }
  auto updated = engine_->update_policy(next);
  if (!updated) {
    response->accepted = false;
    response->error_code = "policy_rejected";
    response->error_message = updated.error().message;
    response->previous_policy_hash = previous;
    response->effective_policy_hash = previous;
    return;
  }
  policy_hash_ = engine_->controller()->policy_hash();
  const auto now_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
                          std::chrono::steady_clock::now().time_since_epoch())
                          .count();
  auto decision = engine_->controller()->evaluate_switch(now_ns);
  if (decision.should_switch) {
    perceptshift::runtime::FrameResult fake;
    fake.last_switch_reason = decision.reason;
    fake.active_profile_id = decision.to_profile_id.value_or("");
    publish_switch_event(fake, sequence_id_.load());
  }
  if (engine_->controller()->active_profile_id()) {
    active_profile_id_ = *engine_->controller()->active_profile_id();
  }
  response->accepted = true;
  response->previous_policy_hash = previous;
  response->effective_policy_hash = policy_hash_;
}

void RuntimeNode::publish_profile_states() {
  if (!profile_pub_ || !profile_pub_->is_activated() || !engine_) {
    return;
  }
  const auto now_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
                          std::chrono::steady_clock::now().time_since_epoch())
                          .count();
  for (auto* p : engine_->registry().all()) {
    perceptshift_msgs::msg::ProfileState msg;
    msg.header.stamp = now();
    msg.profile_id = p->profile_id;
    msg.label = p->label;
    msg.active = engine_->controller() && engine_->controller()->active_profile_id() &&
                 *engine_->controller()->active_profile_id() == p->profile_id;
    const auto el = perceptshift::runtime::evaluate_eligibility(
        *p, engine_->policy(), p->offline_envelope_ms, now_ns, false);
    msg.eligible = el.eligible;
    msg.rejection_reason_codes = el.rejection_reasons;
    msg.certified_quality_value = static_cast<float>(p->certified_quality);
    msg.predicted_latency_bound_ms = static_cast<float>(p->offline_envelope_ms);
    msg.recent_p99_ms = static_cast<float>(p->certified_p99_ms);
    msg.peak_rss_attestation_bytes = static_cast<uint64_t>(std::max<std::int64_t>(0, p->peak_rss_bytes));
    msg.lifecycle_state = p->warmed ? perceptshift_msgs::msg::ProfileState::LIFECYCLE_WARMED
                                    : perceptshift_msgs::msg::ProfileState::LIFECYCLE_LOADED;
    if (msg.active) {
      msg.lifecycle_state = perceptshift_msgs::msg::ProfileState::LIFECYCLE_ACTIVE;
    }
    if (!p->healthy) {
      msg.lifecycle_state = perceptshift_msgs::msg::ProfileState::LIFECYCLE_FAILED;
    }
    if (!el.eligible && !msg.active) {
      msg.lifecycle_state = perceptshift_msgs::msg::ProfileState::LIFECYCLE_INELIGIBLE;
    }
    profile_pub_->publish(msg);
  }
}

void RuntimeNode::publish_switch_event(const perceptshift::runtime::FrameResult& result,
                                       uint64_t sequence_id) {
  if (!switch_pub_ || !switch_pub_->is_activated() || !result.last_switch_reason.has_value()) {
    return;
  }
  perceptshift_msgs::msg::SwitchEvent msg;
  msg.header.stamp = now();
  msg.from_profile_id = result.executed_profile_id;
  msg.to_profile_id = result.next_active_profile_id.empty() ? result.active_profile_id
                                                            : result.next_active_profile_id;
  msg.effective_sequence_id = sequence_id;
  msg.evidence_summary = "controller_switch";
  using SR = perceptshift::runtime::SwitchReason;
  switch (*result.last_switch_reason) {
  case SR::StartupSelect:
    msg.reason_code = perceptshift_msgs::msg::SwitchEvent::REASON_STARTUP;
    break;
  case SR::DeadlineRiskDemotion:
    msg.reason_code = perceptshift_msgs::msg::SwitchEvent::REASON_DEADLINE;
    break;
  case SR::QualityPromotion:
  case SR::ConfidenceEscalation:
    msg.reason_code = perceptshift_msgs::msg::SwitchEvent::REASON_QUALITY;
    break;
  case SR::ManualPin:
  case SR::PinExpired:
    msg.reason_code = perceptshift_msgs::msg::SwitchEvent::REASON_MANUAL_PIN;
    msg.manual = true;
    break;
  case SR::NoEligible:
    msg.reason_code = perceptshift_msgs::msg::SwitchEvent::REASON_FAIL_CLOSED;
    break;
  default:
    msg.reason_code = perceptshift_msgs::msg::SwitchEvent::REASON_POLICY;
    break;
  }
  switch_pub_->publish(msg);
}

void RuntimeNode::publish_inference_trace(const perceptshift::runtime::FrameResult& result,
                                          const perceptshift::runtime::FrameRequest& request) {
  if (!trace_pub_ || !trace_pub_->is_activated()) {
    return;
  }
  perceptshift_msgs::msg::InferenceTrace msg;
  msg.header.stamp = now();
  msg.sequence_id = static_cast<uint64_t>(result.sequence_id);
  msg.profile_id = result.executed_profile_id.empty() ? result.active_profile_id
                                                      : result.executed_profile_id;
  msg.source_timestamp.sec = static_cast<int32_t>(request.source_timestamp_ns / 1'000'000'000LL);
  msg.source_timestamp.nanosec =
      static_cast<uint32_t>(request.source_timestamp_ns % 1'000'000'000LL);
  const auto now_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
                          std::chrono::steady_clock::now().time_since_epoch())
                          .count();
  msg.receive_timestamp = now();
  msg.queue_age_ns = static_cast<uint64_t>(
      std::max<std::int64_t>(0, now_ns - request.receive_steady_ns));
  msg.preprocess_ns = static_cast<uint64_t>(result.preprocess_ms * 1.0e6);
  msg.inference_ns = static_cast<uint64_t>(result.inference_ms * 1.0e6);
  msg.postprocess_ns = static_cast<uint64_t>(result.postprocess_ms * 1.0e6);
  msg.total_ns = static_cast<uint64_t>(result.total_ms * 1.0e6);
  msg.deadline_ns = static_cast<uint64_t>(engine_->policy().deadline_ms * 1.0e6);
  msg.deadline_missed = result.total_ms > engine_->policy().deadline_ms;
  msg.frame_dropped = false;
  msg.input_backend = request.pixel_format;
  if (result.telemetry.contains("preprocess_impl")) {
    msg.preprocess_backend = result.telemetry["preprocess_impl"].get<std::string>();
  }
  msg.execution_provider_summary = result.active_provider_summary;
  trace_pub_->publish(msg);
}

void RuntimeNode::handle_recovery(
    const std::shared_ptr<perceptshift_msgs::srv::RequestRecovery::Request> request,
    std::shared_ptr<perceptshift_msgs::srv::RequestRecovery::Response> response) {
  if (!engine_ || !engine_->controller()) {
    response->accepted = false;
    response->error_code = "recovery_prerequisites_failed";
    response->error_message = "RuntimeEngine not configured";
    response->resulting_health_reason = health_reason_;
    return;
  }
  (void)request;
  const auto now_ns = std::chrono::duration_cast<std::chrono::nanoseconds>(
                          std::chrono::steady_clock::now().time_since_epoch())
                          .count();
  const bool ok = engine_->controller()->request_recovery(now_ns);
  response->accepted = ok;
  if (!ok) {
    response->error_code = "recovery_rejected";
    response->error_message = "controller rejected recovery";
    response->resulting_health_reason = health_reason_;
    return;
  }
  control_hold_requested_ = false;
  health_state_ = perceptshift_msgs::msg::RuntimeHealth::HEALTH_RECOVERING;
  health_reason_ = "recovery_requested";
  response->resulting_health_reason = health_reason_;
}

} // namespace perceptshift_ros

RCLCPP_COMPONENTS_REGISTER_NODE(perceptshift_ros::RuntimeNode)
