#pragma once

#include "perceptshift/profiles/profile_registry.hpp"
#include "perceptshift/result.hpp"
#include "perceptshift/runtime/health_machine.hpp"
#include "perceptshift/runtime/latency_estimator.hpp"
#include "perceptshift/runtime/policy.hpp"
#include "perceptshift/runtime/switch_decision.hpp"

#include <cstdint>
#include <optional>
#include <string>
#include <unordered_map>
#include <vector>

namespace perceptshift::runtime {

struct FrameObservation {
  std::int64_t now_steady_ns{0};
  std::int64_t source_timestamp_ns{0};
  double latency_ms{0.0};
  bool inference_ok{true};
  float confidence_signal{-1.f};
  bool source_stale{false};
};

struct ManualPin {
  std::string profile_id;
  std::int64_t expires_steady_ns{0};
};

class Controller {
public:
  Controller(RuntimePolicy policy, profiles::ProfileRegistry* registry);

  void mark_profile_warmed(const std::string& profile_id);
  void observe(const FrameObservation& obs);
  [[nodiscard]] SwitchDecision evaluate_switch(std::int64_t now_steady_ns);
  bool request_pin(const std::string& profile_id, std::int64_t now_steady_ns, int seconds);
  void clear_pin();
  bool request_recovery(std::int64_t now_steady_ns);
  [[nodiscard]] Result<RuntimePolicy> update_policy(const RuntimePolicy& next);

  [[nodiscard]] const HealthMachine& health() const noexcept { return health_; }
  [[nodiscard]] std::optional<std::string> active_profile_id() const { return active_profile_id_; }
  [[nodiscard]] const RuntimePolicy& policy() const noexcept { return policy_; }
  [[nodiscard]] std::string policy_hash() const;

private:
  std::vector<profiles::Profile*> eligible_profiles(std::int64_t now_steady_ns, bool escalation);
  profiles::Profile* select_best(const std::vector<profiles::Profile*>& eligible,
                                 bool prefer_quality);

  RuntimePolicy policy_;
  profiles::ProfileRegistry* registry_;
  HealthMachine health_;
  std::optional<std::string> active_profile_id_;
  std::unordered_map<std::string, LatencyEstimator> estimators_;
  std::optional<ManualPin> pin_;
  std::int64_t active_since_steady_ns_{0};
  int promotion_streak_{0};
  int demotion_streak_{0};
  int recover_streak_{0};
  std::vector<bool> deadline_miss_window_;
  bool confidence_escalation_active_{false};
};

} // namespace perceptshift::runtime
