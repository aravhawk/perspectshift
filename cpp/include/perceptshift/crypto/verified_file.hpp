#pragma once

#include "perceptshift/crypto/digest.hpp"
#include "perceptshift/result.hpp"
#include "perceptshift/util/file_security.hpp"

#include <filesystem>
#include <optional>
#include <string>
#include <vector>

namespace perceptshift::crypto {

struct VerifiedFile {
  std::filesystem::path path;
  util::FileIdentity identity;
  Sha256Digest digest;
  std::string digest_hex;
  std::vector<std::uint8_t> contents;
};

[[nodiscard]] Result<VerifiedFile>
open_verified_file(const std::filesystem::path& path, const util::FileSecurityPolicy& policy,
                   std::optional<std::string> expected_sha256_hex = std::nullopt);

[[nodiscard]] Result<void> verify_digest_unchanged(const VerifiedFile& verified);

} // namespace perceptshift::crypto
