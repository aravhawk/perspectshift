#include "perceptshift/adapters/classification_adapter.hpp"
#include "perceptshift/adapters/raw_tensor_adapter.hpp"
#include "perceptshift/adapters/yolo_v8_adapter.hpp"

#include <gtest/gtest.h>

TEST(AdapterTest, RawTensor) {
  float data[4] = {1.f, 2.f, 3.f, 4.f};
  perceptshift::adapters::TensorView tv{data, {1, 4}};
  perceptshift::adapters::RawTensorAdapter adapter;
  auto out = adapter.postprocess(tv);
  ASSERT_TRUE(out.ok());
  EXPECT_EQ(out.value().raw_values.size(), 4u);
}

TEST(AdapterTest, ClassificationTopK) {
  float logits[5] = {0.1f, 0.8f, 0.05f, 0.03f, 0.02f};
  perceptshift::adapters::TensorView tv{logits, {1, 5}};
  perceptshift::adapters::ClassificationAdapterConfig cfg;
  cfg.top_k = 2;
  perceptshift::adapters::ClassificationAdapter adapter(cfg);
  auto out = adapter.postprocess(tv);
  ASSERT_TRUE(out.ok());
  ASSERT_EQ(out.value().classifications.size(), 2u);
  EXPECT_EQ(out.value().classifications[0].class_id, 1);
  EXPECT_FLOAT_EQ(out.value().confidence_signal, 0.8f);
}

TEST(AdapterTest, YoloV8FiltersByConfidence) {
  // channels_first [1, 6, 2] => 4 box + 2 classes, 2 anchors
  // YOLO emits center format; Detection stores top-left.
  float data[12] = {
      // c0 x:
      10.f,
      20.f,
      // y
      10.f,
      20.f,
      // w
      4.f,
      4.f,
      // h
      4.f,
      4.f,
      // class0
      0.9f,
      0.1f,
      // class1
      0.05f,
      0.8f,
  };
  perceptshift::adapters::TensorView tv{data, {1, 6, 2}};
  perceptshift::adapters::YoloV8AdapterConfig cfg;
  cfg.confidence_threshold = 0.5f;
  cfg.num_classes = 2;
  cfg.input_width = 64;
  cfg.input_height = 64;
  perceptshift::adapters::YoloV8Adapter adapter(cfg);
  auto out = adapter.postprocess(tv);
  ASSERT_TRUE(out.ok());
  ASSERT_EQ(out.value().detections.size(), 2u);
  // Center (10,10) w/h=4 → top-left (8,8)
  EXPECT_FLOAT_EQ(out.value().detections[0].x, 8.f);
  EXPECT_FLOAT_EQ(out.value().detections[0].y, 8.f);
  EXPECT_FLOAT_EQ(out.value().detections[0].w, 4.f);
  EXPECT_FLOAT_EQ(out.value().detections[0].h, 4.f);
}
