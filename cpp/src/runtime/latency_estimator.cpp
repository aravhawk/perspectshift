#include "perceptshift/runtime/latency_estimator.hpp"

#include <algorithm>
#include <cmath>

namespace perceptshift::runtime {

LatencyEstimator::LatencyEstimator(std::size_t window, double quantile, double mad_multiplier,
                                   double margin_ms)
    : window_(std::max<std::size_t>(window, 8)), quantile_(quantile),
      mad_multiplier_(mad_multiplier), margin_ms_(margin_ms) {
}

void LatencyEstimator::observe_ms(double latency_ms) {
  values_.push_back(latency_ms);
  if (values_.size() > window_) {
    values_.erase(values_.begin());
  }
}

double LatencyEstimator::quantile_ms() const {
  if (values_.empty()) {
    return 0.0;
  }
  std::vector<double> sorted = values_;
  std::sort(sorted.begin(), sorted.end());
  const double pos = quantile_ * static_cast<double>(sorted.size() - 1);
  const std::size_t idx = static_cast<std::size_t>(pos);
  const double frac = pos - static_cast<double>(idx);
  if (idx + 1 >= sorted.size()) {
    return sorted.back();
  }
  return sorted[idx] * (1.0 - frac) + sorted[idx + 1] * frac;
}

double LatencyEstimator::mad_ms() const {
  if (values_.empty()) {
    return 0.0;
  }
  std::vector<double> sorted = values_;
  std::sort(sorted.begin(), sorted.end());
  const double med = sorted[sorted.size() / 2];
  std::vector<double> abs_dev;
  abs_dev.reserve(sorted.size());
  for (double v : sorted) {
    abs_dev.push_back(std::abs(v - med));
  }
  std::sort(abs_dev.begin(), abs_dev.end());
  return abs_dev[abs_dev.size() / 2];
}

double LatencyEstimator::conservative_bound_ms() const {
  return quantile_ms() + mad_multiplier_ * mad_ms() + margin_ms_;
}

} // namespace perceptshift::runtime
