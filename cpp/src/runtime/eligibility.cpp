#include "perceptshift/runtime/eligibility.hpp"

#include <algorithm>
#include <limits>

namespace perceptshift::runtime {

EligibilityResult evaluate_eligibility(const profiles::Profile& profile,
                                       const RuntimePolicy& policy, double online_bound_ms,
                                       std::int64_t now_steady_ns,
                                       bool confidence_escalation_active) {
  (void)confidence_escalation_active;
  EligibilityResult r;
  if (profile.status != profiles::ProfileStatus::Certified) {
    r.rejection_reasons.push_back("NOT_CERTIFIED");
  }
  if (!profile.warmed) {
    r.rejection_reasons.push_back("NOT_WARMED");
  }

  const bool cooling = profile.cooldown_until_steady_ns > now_steady_ns;
  const bool hard_failed =
      profile.cooldown_until_steady_ns == std::numeric_limits<std::int64_t>::max();
  if (cooling) {
    r.rejection_reasons.push_back("COOLDOWN");
  } else if (!profile.healthy) {
    if (hard_failed) {
      r.rejection_reasons.push_back("UNHEALTHY_HARD_FAIL");
    } else if (profile.failure_count >= policy.max_transient_failures_before_operator_recovery) {
      r.rejection_reasons.push_back("UNHEALTHY_REQUIRES_RECOVERY");
    }
    // else: cooldown expired → probation retry allowed (do not reject solely for healthy=false)
  }

  if (profile.certified_quality < policy.minimum_quality_value) {
    r.rejection_reasons.push_back("QUALITY_BELOW_FLOOR");
  }
  const double bound =
      std::max(online_bound_ms, profile.offline_envelope_ms * policy.offline_envelope_weight);
  if (bound > policy.deadline_ms) {
    r.rejection_reasons.push_back("DEADLINE_BOUND_EXCEEDED");
  }

  r.eligible = r.rejection_reasons.empty();
  return r;
}

} // namespace perceptshift::runtime
