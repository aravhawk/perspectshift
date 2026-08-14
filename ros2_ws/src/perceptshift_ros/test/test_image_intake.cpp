// Copyright 2026 PerceptShift Authors
// SPDX-License-Identifier: Apache-2.0

#include "perceptshift_ros/image_intake.hpp"

#include <gtest/gtest.h>
#include <sensor_msgs/msg/image.hpp>

TEST(ImageIntake, AcceptsRgb8) {
  perceptshift_ros::ImageIntake intake;
  sensor_msgs::msg::Image image;
  image.width = 2;
  image.height = 2;
  image.encoding = "rgb8";
  image.step = 6;
  image.data.resize(12, 1);

  const auto result = intake.validate(image);
  ASSERT_TRUE(result.ok);
  ASSERT_EQ(result.view->width, 2u);
}

TEST(ImageIntake, RejectsBadStep) {
  perceptshift_ros::ImageIntake intake;
  sensor_msgs::msg::Image image;
  image.width = 4;
  image.height = 1;
  image.encoding = "rgb8";
  image.step = 2;
  image.data.resize(4, 0);

  const auto result = intake.validate(image);
  ASSERT_FALSE(result.ok);
  ASSERT_EQ(result.reason_code, "invalid_step");
}

TEST(ImageIntake, LatestOnlyDropsPrevious) {
  perceptshift_ros::ImageIntake intake;
  intake.set_capacity(1);

  auto a = std::make_shared<sensor_msgs::msg::Image>();
  a->width = 1;
  a->height = 1;
  a->encoding = "mono8";
  a->step = 1;
  a->data = {1};

  auto b = std::make_shared<sensor_msgs::msg::Image>();
  b->width = 1;
  b->height = 1;
  b->encoding = "mono8";
  b->step = 1;
  b->data = {2};

  ASSERT_TRUE(intake.offer(a));
  ASSERT_TRUE(intake.offer(b));
  ASSERT_EQ(intake.dropped(), 1u);
  auto latest = intake.take_latest();
  ASSERT_TRUE(latest);
  ASSERT_EQ(latest->data[0], 2);
}

int main(int argc, char** argv) {
  ::testing::InitGoogleTest(&argc, argv);
  return RUN_ALL_TESTS();
}
