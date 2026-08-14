#include "perceptshift/adapters/classification_adapter.hpp"

#include <algorithm>
#include <cmath>
#include <numeric>
#include <vector>

namespace perceptshift::adapters {
namespace {

[[nodiscard]] std::vector<float> to_probabilities(const float* data, int classes,
                                                  ClassificationOutputSemantics semantics) {
  std::vector<float> probs(static_cast<std::size_t>(classes));
  if (semantics == ClassificationOutputSemantics::Probabilities) {
    for (int i = 0; i < classes; ++i) {
      probs[static_cast<std::size_t>(i)] = data[i];
    }
    return probs;
  }
  // Numerically stable softmax for logits.
  float max_v = data[0];
  for (int i = 1; i < classes; ++i) {
    max_v = std::max(max_v, data[i]);
  }
  float sum = 0.f;
  for (int i = 0; i < classes; ++i) {
    const float e = std::exp(data[i] - max_v);
    probs[static_cast<std::size_t>(i)] = e;
    sum += e;
  }
  if (sum > 0.f) {
    for (float& p : probs) {
      p /= sum;
    }
  }
  return probs;
}

} // namespace

Result<NormalizedOutput> ClassificationAdapter::postprocess(const TensorView& output) const {
  if (output.data == nullptr || output.shape.empty())
    return Error::make(ErrorCode::PostprocessFailed, "invalid classification tensor");
  const auto classes = static_cast<int>(output.shape.back());
  if (classes <= 0)
    return Error::make(ErrorCode::ModelTensorMismatch, "classification dim must be positive");

  auto probs = to_probabilities(output.data, classes, config_.output_semantics);
  if (config_.output_semantics == ClassificationOutputSemantics::Probabilities) {
    for (float p : probs) {
      if (!std::isfinite(p) || p < -1e-3f || p > 1.0f + 1e-3f) {
        return Error::make(ErrorCode::PostprocessFailed,
                           "classification probabilities must be finite and roughly in [0,1]");
      }
    }
  }

  std::vector<int> idx(static_cast<std::size_t>(classes));
  std::iota(idx.begin(), idx.end(), 0);
  std::partial_sort(idx.begin(), idx.begin() + std::min(config_.top_k, classes), idx.end(),
                    [&](int a, int b) {
                      return probs[static_cast<std::size_t>(a)] > probs[static_cast<std::size_t>(b)];
                    });
  NormalizedOutput out;
  out.task = "image_classification";
  const int k = std::min(config_.top_k, classes);
  for (int i = 0; i < k; ++i) {
    const int id = idx[static_cast<std::size_t>(i)];
    const float score = probs[static_cast<std::size_t>(id)];
    if (score < config_.score_threshold)
      continue;
    Classification c;
    c.class_id = id;
    c.score = score;
    if (auto it = config_.labels.find(id); it != config_.labels.end())
      c.label = it->second;
    out.classifications.push_back(std::move(c));
  }
  out.confidence_signal = out.classifications.empty() ? 0.f : out.classifications.front().score;
  return out;
}
} // namespace perceptshift::adapters
