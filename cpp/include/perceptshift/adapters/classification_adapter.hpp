#pragma once
#include "perceptshift/adapters/adapter.hpp"

#include <string>
#include <unordered_map>

namespace perceptshift::adapters {

enum class ClassificationOutputSemantics { Logits, Probabilities };

struct ClassificationAdapterConfig {
  int top_k{5};
  float score_threshold{0.f};
  ClassificationOutputSemantics output_semantics{ClassificationOutputSemantics::Probabilities};
  std::unordered_map<int, std::string> labels;
};

class ClassificationAdapter final : public Adapter {
public:
  explicit ClassificationAdapter(ClassificationAdapterConfig config) : config_(std::move(config)) {
    if (config_.top_k <= 0)
      config_.top_k = 1;
  }
  [[nodiscard]] std::string name() const override { return "image_classification"; }
  [[nodiscard]] bool provides_confidence_signal() const noexcept override { return true; }
  [[nodiscard]] Result<NormalizedOutput> postprocess(const TensorView& output) const override;

private:
  ClassificationAdapterConfig config_;
};
} // namespace perceptshift::adapters
