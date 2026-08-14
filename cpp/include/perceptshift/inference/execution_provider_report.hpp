#pragma once

#include <optional>
#include <string>
#include <vector>

namespace perceptshift::inference {

struct ExecutionProviderReport {
  std::vector<std::string> requested_providers;
  std::vector<std::string> registered_providers;
  std::vector<std::string> provider_order;
  std::optional<double> xnnpack_node_fraction;
  std::string xnnpack_fraction_unavailable_reason;
  std::vector<std::string> warnings;
  std::string raw_profile_path;
};

} // namespace perceptshift::inference
