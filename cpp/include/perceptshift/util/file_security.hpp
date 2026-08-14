#pragma once

#include "perceptshift/result.hpp"

#include <filesystem>
#include <string>
#include <vector>

namespace perceptshift::util {

struct FileSecurityPolicy {
  bool allow_world_writable{false};
  bool allow_symlinks{false};
  bool require_owner_match{true};
  std::vector<std::filesystem::path> allowed_roots;
  std::uint64_t maximum_size_bytes{0}; // 0 = unlimited
};

struct FileSecurityInfo {
  std::filesystem::path canonical_path;
  bool is_symlink{false};
  bool world_writable{false};
  std::uint64_t size_bytes{0};
};

// Alias used by verified-file and bundle loaders.
using FileIdentity = FileSecurityInfo;

[[nodiscard]] Result<FileSecurityInfo> inspect_path(const std::filesystem::path& path,
                                                    const FileSecurityPolicy& policy);

[[nodiscard]] inline Result<FileSecurityInfo> inspect_file(const std::filesystem::path& path,
                                                           const FileSecurityPolicy& policy) {
  return inspect_path(path, policy);
}

[[nodiscard]] Result<std::filesystem::path>
ensure_within_root(const std::filesystem::path& root, const std::filesystem::path& candidate);

[[nodiscard]] Result<std::filesystem::path> validate_model_path(const std::filesystem::path& path,
                                                                const FileSecurityPolicy& policy);

} // namespace perceptshift::util
