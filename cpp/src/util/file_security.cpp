#include "perceptshift/util/file_security.hpp"

#include <sys/stat.h>
#include <unistd.h>

namespace perceptshift::util {
namespace {

bool is_world_writable(const struct stat& st) {
  return (st.st_mode & S_IWOTH) != 0;
}

} // namespace

Result<std::filesystem::path> ensure_within_root(const std::filesystem::path& root,
                                                 const std::filesystem::path& candidate) {
  std::error_code ec;
  const auto canon_root = std::filesystem::weakly_canonical(root, ec);
  if (ec) {
    return Error::make(ErrorCode::PathUnsafe, "unable to canonicalize root: " + root.string());
  }
  const auto canon_cand = std::filesystem::weakly_canonical(candidate, ec);
  if (ec) {
    return Error::make(ErrorCode::PathUnsafe, "unable to canonicalize path: " + candidate.string());
  }
  const auto root_str = canon_root.string();
  const auto cand_str = canon_cand.string();
  if (cand_str != root_str && cand_str.rfind(root_str + "/", 0) != 0) {
    return Error::make(ErrorCode::PathUnsafe, "path escapes allowed root: " + candidate.string(),
                       "Keep all model and bundle files under configured roots");
  }
  return canon_cand;
}

Result<FileSecurityInfo> inspect_path(const std::filesystem::path& path,
                                      const FileSecurityPolicy& policy) {
  std::error_code ec;
  if (!std::filesystem::exists(path, ec)) {
    return Error::make(ErrorCode::PathUnsafe, "path does not exist: " + path.string());
  }

  const bool is_symlink = std::filesystem::is_symlink(path, ec);
  if (is_symlink && !policy.allow_symlinks) {
    return Error::make(
        ErrorCode::PathUnsafe, "symlinked path rejected: " + path.string(),
        "Disable symlinks or set allow_symlinked_model_files under controlled policy");
  }

  if (!policy.allowed_roots.empty()) {
    bool ok = false;
    Error last = Error::make(ErrorCode::PathUnsafe, "path outside allowed roots");
    for (const auto& root : policy.allowed_roots) {
      auto within = ensure_within_root(root, path);
      if (within) {
        ok = true;
        break;
      }
      last = within.error();
    }
    if (!ok) {
      return last;
    }
  }

  struct stat st{};
  if (::lstat(path.c_str(), &st) != 0) {
    return Error::make(ErrorCode::PathUnsafe, "lstat failed: " + path.string());
  }
  if (is_world_writable(st) && !policy.allow_world_writable) {
    return Error::make(ErrorCode::PathUnsafe, "world-writable file rejected: " + path.string());
  }
  if (policy.require_owner_match) {
    if (st.st_uid != ::geteuid()) {
      return Error::make(ErrorCode::PathUnsafe,
                         "file owner does not match process uid: " + path.string(),
                         "Adjust ownership or disable require_bundle_owner_match intentionally");
    }
  }
  if (policy.maximum_size_bytes > 0 &&
      static_cast<std::uint64_t>(st.st_size) > policy.maximum_size_bytes) {
    return Error::make(ErrorCode::ModelResourceLimit, "file exceeds configured size limit");
  }

  auto canon = std::filesystem::weakly_canonical(path, ec);
  if (ec) {
    return Error::make(ErrorCode::PathUnsafe, "canonicalization failed: " + path.string());
  }
  FileSecurityInfo info;
  info.canonical_path = std::move(canon);
  info.is_symlink = is_symlink;
  info.world_writable = is_world_writable(st);
  info.size_bytes = static_cast<std::uint64_t>(st.st_size);
  return info;
}

Result<std::filesystem::path> validate_model_path(const std::filesystem::path& path,
                                                  const FileSecurityPolicy& policy) {
  auto info = inspect_path(path, policy);
  if (!info) {
    return info.error();
  }
  const auto& p = info.value().canonical_path;
  const auto ext = p.extension().string();
  if (ext != ".onnx") {
    return Error::make(ErrorCode::ModelInvalid, "model path must end with .onnx: " + p.string());
  }
  return p;
}

} // namespace perceptshift::util
