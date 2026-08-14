#include "perceptshift/result.hpp"

#include <gtest/gtest.h>

using perceptshift::Error;
using perceptshift::ErrorCode;
using perceptshift::Result;

TEST(ResultTest, OkValue) {
  Result<int> r(42);
  ASSERT_TRUE(r.ok());
  EXPECT_EQ(r.value(), 42);
}

TEST(ResultTest, ErrorPath) {
  Result<int> r(Error::make(ErrorCode::ConfigInvalid, "bad"));
  ASSERT_FALSE(r.ok());
  EXPECT_EQ(r.error().code, ErrorCode::ConfigInvalid);
}

TEST(ResultVoidTest, Success) {
  auto r = Result<void>::success();
  EXPECT_TRUE(r.ok());
}
