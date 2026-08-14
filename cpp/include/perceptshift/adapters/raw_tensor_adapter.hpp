#pragma once
#include "perceptshift/adapters/adapter.hpp"
namespace perceptshift::adapters {
class RawTensorAdapter final : public Adapter {
public:
  [[nodiscard]] std::string name() const override { return "raw_tensor"; }
  [[nodiscard]] Result<NormalizedOutput> postprocess(const TensorView& output) const override;
};
} // namespace perceptshift::adapters
