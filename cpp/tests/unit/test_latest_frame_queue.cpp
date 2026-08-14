#include "perceptshift/runtime/latest_frame_queue.hpp"

#include <gtest/gtest.h>

TEST(LatestFrameQueueTest, OverwritesAndCountsDrops) {
  perceptshift::runtime::LatestFrameQueue q(1);
  perceptshift::runtime::FrameEnvelope a;
  a.sequence = 1;
  perceptshift::runtime::FrameEnvelope b;
  b.sequence = 2;
  EXPECT_FALSE(q.push(std::move(a)));
  EXPECT_TRUE(q.push(std::move(b)));
  EXPECT_EQ(q.dropped_count(), 1u);
  auto got = q.pop_latest();
  ASSERT_TRUE(got.has_value());
  EXPECT_EQ(got->sequence, 2u);
  EXPECT_FALSE(q.pop_latest().has_value());
}
