#pragma once

#include <cstddef>
#include <cstdint>
#include <vector>

namespace perceptshift::runtime {

class LatencyEstimator {
public:
  LatencyEstimator(std::size_t window, double quantile, double mad_multiplier, double margin_ms);

  void observe_ms(double latency_ms);
  [[nodiscard]] double quantile_ms() const;
  [[nodiscard]] double mad_ms() const;
  [[nodiscard]] double conservative_bound_ms() const;
  [[nodiscard]] std::size_t sample_count() const noexcept { return values_.size(); }

private:
  std::size_t window_;
  double quantile_;
  double mad_multiplier_;
  double margin_ms_;
  std::vector<double> values_;
};

} // namespace perceptshift::runtime
