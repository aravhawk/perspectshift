#pragma once

#include "perceptshift/profiles/profile.hpp"
#include "perceptshift/result.hpp"
#include "perceptshift/util/file_security.hpp"

#include <cstdint>
#include <filesystem>
#include <nlohmann/json.hpp>
#include <optional>
#include <string>
#include <string_view>
#include <vector>

namespace perceptshift::bundle {

enum class SignaturePolicy {
  Disabled,
  Optional,
  Required,
};

struct SignatureInfo {
  bool present{false};
  bool verified{false};
  std::string algorithm;
  std::string key_id;
  std::string payload_schema_version;
  std::string encoding;
};

struct BundleLoadOptions {
  SignaturePolicy signature_policy{SignaturePolicy::Optional};
  std::vector<std::uint8_t> verify_public_key;
  std::vector<std::string> trusted_key_ids;
  bool strict_inventory{true};
  util::FileSecurityPolicy security{};
};

struct InventoryEntry {
  std::string relative_path;
  std::string sha256_hex;
  std::uint64_t size_bytes{0};
  std::filesystem::path absolute_path;
};

// Compatibility alias used by older call sites.
using BundleFileEntry = InventoryEntry;

struct LoadedBundle {
  std::filesystem::path root;
  nlohmann::json manifest;
  std::string manifest_sha256_hex;
  std::string bundle_id;
  std::string adapter_name;
  std::string quality_metric_name;
  std::string quality_direction{"higher_is_better"};
  nlohmann::json runtime_policy_defaults = nlohmann::json::object();
  std::vector<profiles::Profile> profiles;
  std::vector<nlohmann::json> profile_documents;
  std::vector<InventoryEntry> files;
  SignatureInfo signature;
};

[[nodiscard]] inline const char* to_string(SignaturePolicy p) noexcept {
  switch (p) {
  case SignaturePolicy::Disabled:
    return "disabled";
  case SignaturePolicy::Optional:
    return "optional";
  case SignaturePolicy::Required:
    return "required";
  }
  return "unknown";
}

[[nodiscard]] Result<SignaturePolicy> parse_signature_policy(std::string_view text);

[[nodiscard]] Result<std::vector<std::uint8_t>>
load_ed25519_public_key(const std::filesystem::path& path);

[[nodiscard]] Result<LoadedBundle> load_bundle(const std::filesystem::path& bundle_root,
                                               const BundleLoadOptions& options);

[[nodiscard]] Result<nlohmann::json> verify_bundle_report(const std::filesystem::path& bundle_root,
                                                          const BundleLoadOptions& options);

} // namespace perceptshift::bundle
