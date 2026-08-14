#include "perceptshift/runtime/controller.hpp"

#include "perceptshift/runtime/eligibility.hpp"
#include "perceptshift/runtime/policy_loader.hpp"

#include <algorithm>

namespace perceptshift::runtime {

Controller::Controller(RuntimePolicy policy, profiles::ProfileRegistry* registry)
    : policy_(std::move(policy)), registry_(registry) {
  deadline_miss_window_.reserve(static_cast<std::size_t>(policy_.deadline_miss_window_frames));
}

void Controller::mark_profile_warmed(const std::string& profile_id) {
  if (auto* p = registry_->find(profile_id)) {
    p->warmed = true;
    estimators_.try_emplace(
        profile_id, LatencyEstimator(static_cast<std::size_t>(policy_.latency_window_samples),
                                     policy_.latency_quantile, policy_.latency_mad_multiplier,
                                     policy_.latency_margin_ms));
  }
}

std::vector<profiles::Profile*> Controller::eligible_profiles(std::int64_t now_steady_ns,
                                                              bool escalation) {
  std::vector<profiles::Profile*> out;
  for (auto* p : registry_->all()) {
    double bound = p->offline_envelope_ms;
    if (auto it = estimators_.find(p->profile_id);
        it != estimators_.end() && it->second.sample_count() > 0) {
      bound = std::max(bound, it->second.conservative_bound_ms());
    }
    const auto el = evaluate_eligibility(*p, policy_, bound, now_steady_ns, escalation);
    if (el.eligible) {
      out.push_back(p);
    }
  }
  return out;
}

profiles::Profile* Controller::select_best(const std::vector<profiles::Profile*>& eligible,
                                           bool prefer_quality) {
  if (eligible.empty()) {
    return nullptr;
  }
  auto better = [&](profiles::Profile* a, profiles::Profile* b) {
    if (prefer_quality) {
      if (a->certified_quality != b->certified_quality) {
        return a->certified_quality > b->certified_quality;
      }
    }
    if (a->utility != b->utility) {
      return a->utility > b->utility;
    }
    return a->certified_p99_ms < b->certified_p99_ms;
  };
  profiles::Profile* best = eligible.front();
  for (auto* p : eligible) {
    if (better(p, best)) {
      best = p;
    }
  }
  return best;
}

void Controller::observe(const FrameObservation& obs) {
  if (obs.source_stale && policy_.fail_closed_on_stale_input) {
    health_.set_fail_closed("INPUT_STALE");
    return;
  }
  if (!active_profile_id_) {
    return;
  }
  auto* active = registry_->find(*active_profile_id_);
  if (active == nullptr) {
    return;
  }
  if (!obs.inference_ok) {
    active->healthy = false;
    ++active->failure_count;
    active->cooldown_until_steady_ns = obs.now_steady_ns + 2'000'000'000LL;
    health_.set_degraded("INFERENCE_FAILED");
  } else {
    // Successful frame restores health after probation/cooldown.
    active->healthy = true;
    if (auto it = estimators_.find(*active_profile_id_); it != estimators_.end()) {
      it->second.observe_ms(obs.latency_ms);
    }
  }

  const bool miss = obs.latency_ms > policy_.deadline_ms;
  deadline_miss_window_.push_back(miss);
  if (deadline_miss_window_.size() >
      static_cast<std::size_t>(std::max(0, policy_.deadline_miss_window_frames))) {
    deadline_miss_window_.erase(deadline_miss_window_.begin());
  }

  if (policy_.confidence_escalation_enabled && obs.confidence_signal >= 0.f) {
    confidence_escalation_active_ =
        obs.confidence_signal < static_cast<float>(policy_.confidence_escalation_threshold);
  }

  if (health_.state() == HealthState::Recovering) {
    if (obs.inference_ok && !miss) {
      ++recover_streak_;
      if (recover_streak_ >= policy_.recover_confirmation_frames) {
        health_.set_ready("RECOVERY_CONFIRMED");
        recover_streak_ = 0;
      }
    } else {
      recover_streak_ = 0;
    }
  }
}

SwitchDecision Controller::evaluate_switch(std::int64_t now_steady_ns) {
  SwitchDecision d;

  if (pin_) {
    if (pin_->expires_steady_ns <= now_steady_ns) {
      pin_.reset();
      d.reason = SwitchReason::PinExpired;
    } else if (auto* pinned = registry_->find(pin_->profile_id)) {
      auto el = evaluate_eligibility(*pinned, policy_, pinned->offline_envelope_ms, now_steady_ns,
                                     confidence_escalation_active_);
      if (el.eligible) {
        if (!active_profile_id_ || *active_profile_id_ != pinned->profile_id) {
          d.should_switch = true;
          d.from_profile_id = active_profile_id_;
          d.to_profile_id = pinned->profile_id;
          d.reason = SwitchReason::ManualPin;
          d.evidence = "manual_pin_active";
          active_profile_id_ = pinned->profile_id;
          active_since_steady_ns_ = now_steady_ns;
          health_.set_ready("PINNED_PROFILE");
        }
        return d;
      }
    }
  }

  auto eligible = eligible_profiles(now_steady_ns, confidence_escalation_active_);
  if (eligible.empty()) {
    if (policy_.fail_closed_on_no_eligible_profile) {
      health_.set_fail_closed("NO_ELIGIBLE_PROFILE");
    }
    d.reason = SwitchReason::NoEligible;
    d.evidence = "no_eligible_profile";
    active_profile_id_.reset();
    return d;
  }

  auto* best = select_best(eligible, confidence_escalation_active_);
  if (!active_profile_id_) {
    d.should_switch = true;
    d.to_profile_id = best->profile_id;
    d.reason = SwitchReason::StartupSelect;
    d.evidence = "initial_selection";
    active_profile_id_ = best->profile_id;
    active_since_steady_ns_ = now_steady_ns;
    health_.set_ready("STARTUP_PROFILE_SELECTED");
    return d;
  }

  if (*active_profile_id_ == best->profile_id) {
    promotion_streak_ = 0;
    demotion_streak_ = 0;
    if (health_.state() == HealthState::FailClosed) {
      // stay fail-closed until recovery
    } else if (health_.state() != HealthState::Ready &&
               health_.state() != HealthState::Recovering) {
      health_.set_ready("ACTIVE_PROFILE_STABLE");
    }
    return d;
  }

  auto* active = registry_->find(*active_profile_id_);
  const bool active_still_eligible =
      active != nullptr && std::any_of(eligible.begin(), eligible.end(), [&](profiles::Profile* p) {
        return p->profile_id == active->profile_id;
      });

  int miss_count = 0;
  for (bool m : deadline_miss_window_) {
    if (m)
      ++miss_count;
  }
  const bool deadline_risk = miss_count >= policy_.deadline_miss_threshold;

  const double dwell_ms =
      static_cast<double>(now_steady_ns - active_since_steady_ns_) / 1'000'000.0;
  const bool dwell_ok = dwell_ms >= policy_.minimum_dwell_ms;

  const bool demote =
      deadline_risk || !active_still_eligible || (active != nullptr && !active->healthy);
  if (demote) {
    ++demotion_streak_;
    promotion_streak_ = 0;
    if (demotion_streak_ >= policy_.demotion_confirmation_frames) {
      d.should_switch = true;
      d.from_profile_id = active_profile_id_;
      d.to_profile_id = best->profile_id;
      d.reason =
          deadline_risk ? SwitchReason::DeadlineRiskDemotion : SwitchReason::ProfileUnhealthy;
      d.evidence = "demotion_confirmed";
      active_profile_id_ = best->profile_id;
      active_since_steady_ns_ = now_steady_ns;
      demotion_streak_ = 0;
      health_.set_degraded("PROFILE_SWITCH_DEMOTION");
    }
    return d;
  }

  // Promotion path: higher utility/quality candidate
  if (dwell_ok && best->utility > (active ? active->utility : -1e9)) {
    ++promotion_streak_;
    demotion_streak_ = 0;
    if (promotion_streak_ >= policy_.promotion_confirmation_frames) {
      d.should_switch = true;
      d.from_profile_id = active_profile_id_;
      d.to_profile_id = best->profile_id;
      d.reason = confidence_escalation_active_ ? SwitchReason::ConfidenceEscalation
                                               : SwitchReason::QualityPromotion;
      d.evidence = "promotion_confirmed";
      active_profile_id_ = best->profile_id;
      active_since_steady_ns_ = now_steady_ns;
      promotion_streak_ = 0;
      health_.set_ready("PROFILE_SWITCH_PROMOTION");
    }
  } else {
    promotion_streak_ = 0;
  }
  return d;
}

bool Controller::request_pin(const std::string& profile_id, std::int64_t now_steady_ns,
                             int seconds) {
  if (seconds <= 0 || seconds > policy_.manual_pin_maximum_seconds) {
    return false;
  }
  if (registry_->find(profile_id) == nullptr) {
    return false;
  }
  pin_ =
      ManualPin{profile_id, now_steady_ns + static_cast<std::int64_t>(seconds) * 1'000'000'000LL};
  return true;
}

void Controller::clear_pin() {
  pin_.reset();
}

bool Controller::request_recovery(std::int64_t /*now_steady_ns*/) {
  if (health_.state() != HealthState::FailClosed && health_.state() != HealthState::Degraded) {
    return false;
  }
  recover_streak_ = 0;
  health_.begin_recovery("OPERATOR_RECOVERY_REQUEST");
  health_.clear_control_hold();
  for (auto* p : registry_->all()) {
    if (p->status == profiles::ProfileStatus::Certified) {
      p->healthy = true;
      p->failure_count = 0;
      p->cooldown_until_steady_ns = 0;
    }
  }
  return true;
}

Result<RuntimePolicy> Controller::update_policy(const RuntimePolicy& next) {
  auto validated = validate_runtime_policy(next);
  if (!validated) {
    return validated.error();
  }
  policy_ = validated.value();
  deadline_miss_window_.clear();
  deadline_miss_window_.reserve(static_cast<std::size_t>(policy_.deadline_miss_window_frames));
  return policy_;
}

std::string Controller::policy_hash() const {
  return runtime_policy_hash(policy_);
}

} // namespace perceptshift::runtime
