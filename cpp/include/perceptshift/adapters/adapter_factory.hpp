#pragma once
#include "perceptshift/adapters/adapter.hpp"
#include "perceptshift/result.hpp"

#include <memory>
#include <nlohmann/json.hpp>
#include <string>

namespace perceptshift::adapters {
[[nodiscard]] Result<std::unique_ptr<Adapter>> create_adapter(const std::string& name);
[[nodiscard]] Result<std::unique_ptr<Adapter>> create_adapter(const std::string& name,
                                                              const nlohmann::json& config);
} // namespace perceptshift::adapters
