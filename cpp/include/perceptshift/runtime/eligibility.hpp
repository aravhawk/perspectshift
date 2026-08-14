#pragma once

#include "perceptshift/profiles/profile.hpp"
#include "perceptshift/runtime/policy.hpp"

#include <string>
#include <vector>

namespace perceptshift::runtime {

struct EligibilityResult {
  bool eligible{false};
  std::vector<std::string> rejection_reasons;
};

[[nodiscard]] EligibilityResult evaluate_eligibility(const profiles::Profile& profile,
                                                     const RuntimePolicy& policy,
                                                     double online_bound_ms,
                                                     std::int64_t now_steady_ns,
                                                     bool confidence_escalation_active);

} // namespace perceptshift::runtime
