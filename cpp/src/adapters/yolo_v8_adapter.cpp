#include "perceptshift/adapters/yolo_v8_adapter.hpp"

#include <algorithm>
#include <cmath>
namespace perceptshift::adapters {
namespace {
// Detection.{x,y,w,h} is top-left + size in model input pixel space.
float iou(const Detection& a, const Detection& b) {
  const float ax1 = a.x, ay1 = a.y, ax2 = a.x + a.w, ay2 = a.y + a.h;
  const float bx1 = b.x, by1 = b.y, bx2 = b.x + b.w, by2 = b.y + b.h;
  const float ix1 = std::max(ax1, bx1), iy1 = std::max(ay1, by1), ix2 = std::min(ax2, bx2),
              iy2 = std::min(ay2, by2);
  const float iw = std::max(0.f, ix2 - ix1), ih = std::max(0.f, iy2 - iy1), inter = iw * ih;
  const float uni = a.w * a.h + b.w * b.h - inter;
  return uni > 0.f ? inter / uni : 0.f;
}
std::vector<Detection> nms(std::vector<Detection> dets, float iou_thresh, int max_det) {
  std::sort(dets.begin(), dets.end(),
            [](const Detection& a, const Detection& b) { return a.score > b.score; });
  std::vector<Detection> keep;
  std::vector<bool> removed(dets.size(), false);
  for (std::size_t i = 0; i < dets.size(); ++i) {
    if (removed[i])
      continue;
    keep.push_back(dets[i]);
    if (max_det >= 0 && keep.size() >= static_cast<std::size_t>(max_det))
      break;
    for (std::size_t j = i + 1; j < dets.size(); ++j) {
      if (!removed[j] && dets[i].class_id == dets[j].class_id && iou(dets[i], dets[j]) > iou_thresh)
        removed[j] = true;
    }
  }
  return keep;
}

void clamp_box(Detection& d, float max_w, float max_h) {
  float x_min = d.x;
  float y_min = d.y;
  float x_max = d.x + d.w;
  float y_max = d.y + d.h;
  x_min = std::clamp(x_min, 0.f, max_w);
  y_min = std::clamp(y_min, 0.f, max_h);
  x_max = std::clamp(x_max, 0.f, max_w);
  y_max = std::clamp(y_max, 0.f, max_h);
  d.x = x_min;
  d.y = y_min;
  d.w = std::max(0.f, x_max - x_min);
  d.h = std::max(0.f, y_max - y_min);
}
} // namespace
Result<NormalizedOutput> YoloV8Adapter::postprocess(const TensorView& output) const {
  if (output.data == nullptr || output.shape.size() < 2)
    return Error::make(ErrorCode::PostprocessFailed, "invalid YOLO tensor rank");
  std::int64_t channels = 0, anchors = 0;
  bool channels_first = true;
  const std::int64_t expected_channels = 4 + static_cast<std::int64_t>(config_.num_classes);
  if (output.shape.size() == 3) {
    if (output.shape[1] == expected_channels) {
      channels = output.shape[1];
      anchors = output.shape[2];
      channels_first = true;
    } else if (output.shape[2] == expected_channels) {
      anchors = output.shape[1];
      channels = output.shape[2];
      channels_first = false;
    } else if (output.shape[1] <= output.shape[2]) {
      channels = output.shape[1];
      anchors = output.shape[2];
      channels_first = true;
    } else {
      anchors = output.shape[1];
      channels = output.shape[2];
      channels_first = false;
    }
  } else if (output.shape.size() == 2) {
    channels = output.shape[0];
    anchors = output.shape[1];
  } else
    return Error::make(ErrorCode::ModelTensorMismatch, "unsupported YOLO tensor shape");
  if (channels < 5)
    return Error::make(ErrorCode::ModelTensorMismatch, "YOLO channels must be >= 5");
  const int num_classes = static_cast<int>(channels - 4);
  std::vector<Detection> dets;
  auto at = [&](std::int64_t c, std::int64_t a) -> float {
    return channels_first ? output.data[c * anchors + a] : output.data[a * channels + c];
  };
  const float model_w = std::max(1.f, config_.input_width);
  const float model_h = std::max(1.f, config_.input_height);
  for (std::int64_t a = 0; a < anchors; ++a) {
    float best_score = 0.f;
    int best_cls = 0;
    for (int c = 0; c < num_classes; ++c) {
      float s = at(4 + c, a);
      if (s > best_score) {
        best_score = s;
        best_cls = c;
      }
    }
    if (best_score < config_.confidence_threshold)
      continue;
    // YOLO emits center_x, center_y, width, height. Canonical Detection uses top-left.
    float cx = at(0, a);
    float cy = at(1, a);
    float w = at(2, a);
    float h = at(3, a);
    if (config_.coordinate_space == "normalized_0_1") {
      cx *= model_w;
      cy *= model_h;
      w *= model_w;
      h *= model_h;
    }
    Detection d;
    d.x = cx - w * 0.5f;
    d.y = cy - h * 0.5f;
    d.w = w;
    d.h = h;
    clamp_box(d, model_w, model_h);
    d.score = best_score;
    d.class_id = best_cls;
    if (auto it = config_.labels.find(best_cls); it != config_.labels.end())
      d.label = it->second;
    dets.push_back(d);
  }
  NormalizedOutput out;
  out.task = "yolo_v8_detection";
  out.detections = nms(std::move(dets), config_.iou_threshold, config_.max_detections);
  out.confidence_signal = out.detections.empty() ? 0.f : out.detections.front().score;
  return out;
}
} // namespace perceptshift::adapters
