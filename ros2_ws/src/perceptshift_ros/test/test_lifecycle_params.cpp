// Copyright 2026 PerceptShift Authors
// SPDX-License-Identifier: Apache-2.0

#include "perceptshift_ros/runtime_node.hpp"

#include <gtest/gtest.h>

TEST(LifecycleParams, DefaultsAreDeadlineAware) {
  perceptshift_ros::RuntimeParameters params;
  EXPECT_GT(params.deadline_ms, 0.0);
  EXPECT_EQ(params.queue_policy, "latest_only");
  EXPECT_FALSE(params.enable_mutation_services);
}

int main(int argc, char** argv) {
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
