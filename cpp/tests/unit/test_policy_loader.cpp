#include "perceptshift/runtime/policy_loader.hpp"

#include <gtest/gtest.h>

TEST(PolicyLoaderTest, LoadsDeadlineOverride) {
  nlohmann::json doc{{"deadline_ms", 42.5}, {"minimum_dwell_ms", 1000.0}};
  auto policy = perceptshift::runtime::load_runtime_policy_json(doc);
  ASSERT_TRUE(policy.ok()) << policy.error().message;
  EXPECT_DOUBLE_EQ(policy.value().deadline_ms, 42.5);
  EXPECT_DOUBLE_EQ(policy.value().minimum_dwell_ms, 1000.0);
}

TEST(PolicyLoaderTest, RejectsNonObject) {
  auto policy = perceptshift::runtime::load_runtime_policy_json(nlohmann::json::array());
  EXPECT_FALSE(policy.ok());
}
