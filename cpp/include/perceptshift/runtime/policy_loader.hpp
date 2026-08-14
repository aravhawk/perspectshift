#pragma once

#include "perceptshift/result.hpp"
#include "perceptshift/runtime/policy.hpp"

#include <filesystem>
#include <nlohmann/json.hpp>

namespace perceptshift::runtime {

[[nodiscard]] RuntimePolicy default_runtime_policy();

[[nodiscard]] Result<RuntimePolicy> load_runtime_policy_json(const nlohmann::json& document);

[[nodiscard]] Result<RuntimePolicy> load_runtime_policy_file(const std::filesystem::path& path);

[[nodiscard]] RuntimePolicy merge_runtime_policy(RuntimePolicy base, const nlohmann::json& overlay);

[[nodiscard]] nlohmann::json runtime_policy_to_json(const RuntimePolicy& policy);
[[nodiscard]] std::string runtime_policy_hash(const RuntimePolicy& policy);
[[nodiscard]] Result<RuntimePolicy> validate_runtime_policy(const RuntimePolicy& policy);

} // namespace perceptshift::runtime
