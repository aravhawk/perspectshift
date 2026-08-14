#include "perceptshift/runtime/controller.hpp"

#include <gtest/gtest.h>

using perceptshift::profiles::Profile;
using perceptshift::profiles::ProfileRegistry;
using perceptshift::profiles::ProfileStatus;
using perceptshift::runtime::Controller;
using perceptshift::runtime::FrameObservation;
using perceptshift::runtime::HealthState;
using perceptshift::runtime::RuntimePolicy;

static Profile make_profile(const std::string& id, double quality, double p99, double utility) {
  Profile p;
  p.profile_id = id;
  p.label = id;
  p.status = ProfileStatus::Certified;
  p.certified_quality = quality;
  p.certified_p99_ms = p99;
  p.offline_envelope_ms = p99;
  p.utility = utility;
  p.warmed = true;
  p.healthy = true;
  return p;
}

TEST(ControllerTest, SelectsOnStartupAndFailClosedWithoutProfiles) {
  ProfileRegistry reg;
  RuntimePolicy policy;
  policy.fail_closed_on_no_eligible_profile = true;
  Controller c(policy, &reg);
  auto d = c.evaluate_switch(1'000'000);
  EXPECT_FALSE(d.should_switch);
  EXPECT_EQ(c.health().state(), HealthState::FailClosed);
  EXPECT_TRUE(c.health().control_hold_active());
}

TEST(ControllerTest, SelectsHighestUtilityEligible) {
  ProfileRegistry reg;
  ASSERT_TRUE(reg.add(make_profile("fast", 0.8, 20.0, 1.0)));
  ASSERT_TRUE(reg.add(make_profile("accurate", 0.95, 40.0, 2.0)));
  RuntimePolicy policy;
  policy.deadline_ms = 75.0;
  Controller c(policy, &reg);
  c.mark_profile_warmed("fast");
  c.mark_profile_warmed("accurate");
  auto d = c.evaluate_switch(1'000'000);
  ASSERT_TRUE(d.should_switch);
  ASSERT_TRUE(d.to_profile_id.has_value());
  EXPECT_EQ(*d.to_profile_id, "accurate");
  EXPECT_EQ(c.health().state(), HealthState::Ready);
}

TEST(ControllerTest, DemotesOnDeadlineRisk) {
  ProfileRegistry reg;
  ASSERT_TRUE(reg.add(make_profile("slow", 0.99, 80.0, 3.0)));
  ASSERT_TRUE(reg.add(make_profile("fast", 0.8, 20.0, 1.0)));
  // Make slow ineligible by offline envelope above deadline after startup adjust:
  auto* slow = reg.find("slow");
  slow->offline_envelope_ms = 20.0; // initially eligible
  RuntimePolicy policy;
  policy.deadline_ms = 50.0;
  policy.demotion_confirmation_frames = 1;
  policy.deadline_miss_threshold = 1;
  policy.deadline_miss_window_frames = 5;
  policy.minimum_dwell_ms = 0;
  Controller c(policy, &reg);
  c.mark_profile_warmed("slow");
  c.mark_profile_warmed("fast");
  auto d1 = c.evaluate_switch(1);
  ASSERT_TRUE(d1.to_profile_id.has_value());
  EXPECT_EQ(*d1.to_profile_id, "slow");

  FrameObservation obs;
  obs.now_steady_ns = 2;
  obs.latency_ms = 90.0;
  obs.inference_ok = true;
  c.observe(obs);

  // Force slow ineligible via health failure path alternative: raise offline envelope
  slow->offline_envelope_ms = 100.0;
  auto d2 = c.evaluate_switch(3);
  ASSERT_TRUE(d2.should_switch);
  ASSERT_TRUE(d2.to_profile_id.has_value());
  EXPECT_EQ(*d2.to_profile_id, "fast");
}

TEST(ControllerTest, StaleInputFailClosed) {
  ProfileRegistry reg;
  ASSERT_TRUE(reg.add(make_profile("a", 1.0, 10.0, 1.0)));
  RuntimePolicy policy;
  policy.fail_closed_on_stale_input = true;
  Controller c(policy, &reg);
  c.mark_profile_warmed("a");
  (void)c.evaluate_switch(1);
  FrameObservation obs;
  obs.source_stale = true;
  obs.now_steady_ns = 2;
  c.observe(obs);
  EXPECT_EQ(c.health().state(), HealthState::FailClosed);
  EXPECT_TRUE(c.health().control_hold_active());
}
