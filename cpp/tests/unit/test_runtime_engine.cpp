#include "perceptshift/runtime/runtime_engine.hpp"

#include <gtest/gtest.h>

TEST(RuntimeEngineTest, ConfigureRequiresBundlePath) {
  perceptshift::runtime::RuntimeEngine engine;
  perceptshift::runtime::RuntimeEngineConfig cfg;
  auto result = engine.configure(cfg);
  ASSERT_FALSE(result.ok());
  EXPECT_EQ(result.error().code, perceptshift::ErrorCode::ConfigInvalid);
}
