#pragma once
#include <cstddef>
#include <vector>
namespace perceptshift::image {
class TensorBuffer {
public:
  void resize_floats(std::size_t count) { floats_.assign(count, 0.f); }
  [[nodiscard]] float* data() noexcept { return floats_.data(); }
  [[nodiscard]] const float* data() const noexcept { return floats_.data(); }
  [[nodiscard]] std::size_t size() const noexcept { return floats_.size(); }
  [[nodiscard]] std::vector<float>& storage() noexcept { return floats_; }
  [[nodiscard]] const std::vector<float>& storage() const noexcept { return floats_; }

private:
  std::vector<float> floats_;
};
} // namespace perceptshift::image
