#pragma once

#include "perceptshift/adapters/adapter.hpp"
#include "perceptshift/bundle/bundle_loader.hpp"
#include "perceptshift/inference/session_factory.hpp"
#include "perceptshift/inference/session_pool.hpp"
#include "perceptshift/profiles/profile_registry.hpp"
#include "perceptshift/result.hpp"
#include "perceptshift/runtime/controller.hpp"
#include "perceptshift/runtime/frame_request.hpp"
#include "perceptshift/runtime/frame_result.hpp"
#include "perceptshift/runtime/latest_frame_queue.hpp"
#include "perceptshift/runtime/policy.hpp"

#include <filesystem>
#include <memory>
#include <nlohmann/json.hpp>
#include <optional>
#include <string>
#include <unordered_map>
#include <vector>

namespace perceptshift::runtime {

struct RuntimeEngineConfig {
  std::filesystem::path bundle_path;
  std::optional<std::filesystem::path> policy_path;
  bundle::SignaturePolicy signature_policy{bundle::SignaturePolicy::Optional};
  std::optional<std::filesystem::path> verify_key_path;
  std::vector<std::string> trusted_key_ids;
  int warmup_iterations{1};
  bool strict_inventory{true};
  bool allow_symlinks{false};
  // When true, FrameInputKind::ZerosSmoke is permitted (warmup / named smoke only).
  bool allow_zeros_smoke{false};
};

class RuntimeEngine {
public:
  RuntimeEngine() = default;
  RuntimeEngine(const RuntimeEngine&) = delete;
  RuntimeEngine& operator=(const RuntimeEngine&) = delete;

  [[nodiscard]] Result<void> configure(const RuntimeEngineConfig& config);
  [[nodiscard]] Result<nlohmann::json> verify_bundle_only();
  [[nodiscard]] Result<void> load_and_warmup();
  [[nodiscard]] Result<FrameResult> execute_frame(const FrameRequest& request);
  [[nodiscard]] Result<std::vector<FrameResult>>
  execute_input_manifest(const std::filesystem::path& input_manifest_path);

  [[nodiscard]] bool configured() const noexcept { return configured_; }
  [[nodiscard]] bool ready() const noexcept { return ready_; }
  [[nodiscard]] bool control_hold_active() const;
  [[nodiscard]] const Controller* controller() const noexcept { return controller_.get(); }
  [[nodiscard]] Controller* controller() noexcept { return controller_.get(); }
  [[nodiscard]] const profiles::ProfileRegistry& registry() const noexcept { return registry_; }
  [[nodiscard]] const bundle::LoadedBundle* bundle() const noexcept {
    return bundle_ ? &*bundle_ : nullptr;
  }
  [[nodiscard]] const RuntimePolicy& policy() const noexcept { return policy_; }
  [[nodiscard]] Result<RuntimePolicy> update_policy(const RuntimePolicy& next);
  [[nodiscard]] LatestFrameQueue& frame_queue() noexcept { return frame_queue_; }
  [[nodiscard]] nlohmann::json status_json() const;

private:
  [[nodiscard]] Result<void> create_sessions();
  [[nodiscard]] Result<inference::SessionCreateRequest>
  session_request_for_profile(const profiles::Profile& profile,
                              const nlohmann::json& profile_doc) const;
  [[nodiscard]] Result<FrameResult> run_active_inference(const FrameRequest& request);

  RuntimeEngineConfig config_{};
  RuntimePolicy policy_{};
  std::optional<bundle::LoadedBundle> bundle_;
  profiles::ProfileRegistry registry_;
  inference::SessionPool pool_;
  std::unique_ptr<Controller> controller_;
  std::unique_ptr<adapters::Adapter> adapter_;
  std::unordered_map<std::string, nlohmann::json> profile_docs_;
  LatestFrameQueue frame_queue_{1};
  bool configured_{false};
  bool ready_{false};
};

} // namespace perceptshift::runtime
