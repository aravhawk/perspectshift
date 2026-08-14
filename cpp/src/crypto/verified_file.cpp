#include "perceptshift/crypto/verified_file.hpp"

#include <fstream>

namespace perceptshift::crypto {
namespace {

bool constant_time_equal(const Sha256Digest& a, const Sha256Digest& b) noexcept {
  unsigned char diff = 0;
  for (std::size_t i = 0; i < a.size(); ++i) {
    diff = static_cast<unsigned char>(diff | (a[i] ^ b[i]));
  }
  return diff == 0;
}

Result<std::vector<std::uint8_t>> read_file_bytes(const std::filesystem::path& path,
                                                  const util::FileSecurityPolicy& policy) {
  auto info = util::inspect_path(path, policy);
  if (!info) {
    return Err<std::vector<std::uint8_t>>(info.error());
  }
  std::ifstream in(path, std::ios::binary);
  if (!in) {
    return Err<std::vector<std::uint8_t>>(ErrorCode::PathUnsafe,
                                          "unable to open file: " + path.string());
  }
  std::vector<std::uint8_t> bytes(static_cast<std::size_t>(info.value().size_bytes));
  if (!bytes.empty()) {
    in.read(reinterpret_cast<char*>(bytes.data()), static_cast<std::streamsize>(bytes.size()));
    if (static_cast<std::size_t>(in.gcount()) != bytes.size()) {
      return Err<std::vector<std::uint8_t>>(ErrorCode::FileIntegrityFailed,
                                            "short read while loading file");
    }
  }
  return Ok(std::move(bytes));
}

} // namespace

Result<VerifiedFile> open_verified_file(const std::filesystem::path& path,
                                        const util::FileSecurityPolicy& policy,
                                        std::optional<std::string> expected_sha256_hex) {
  auto info = util::inspect_path(path, policy);
  if (!info) {
    return Err<VerifiedFile>(info.error());
  }
  auto bytes = read_file_bytes(path, policy);
  if (!bytes) {
    return Err<VerifiedFile>(bytes.error());
  }
  auto dig = sha256_bytes(bytes.value().data(), bytes.value().size());
  if (!dig) {
    return Err<VerifiedFile>(dig.error());
  }
  VerifiedFile out;
  out.path = path;
  out.identity = util::FileIdentity{
      .canonical_path = info.value().canonical_path,
      .is_symlink = info.value().is_symlink,
      .world_writable = info.value().world_writable,
      .size_bytes = info.value().size_bytes,
  };
  out.digest = dig.value();
  out.digest_hex = to_hex(out.digest);
  if (expected_sha256_hex.has_value()) {
    auto expected = from_hex(*expected_sha256_hex);
    if (!expected) {
      return Err<VerifiedFile>(expected.error());
    }
    if (!constant_time_equal(out.digest, expected.value())) {
      return Err<VerifiedFile>(ErrorCode::FileIntegrityFailed, "SHA-256 mismatch",
                               "Re-download or regenerate the bundle");
    }
  }
  out.contents = std::move(bytes.value());
  return Ok(std::move(out));
}

Result<void> verify_digest_unchanged(const VerifiedFile& verified) {
  auto dig = sha256_file(verified.path.string());
  if (!dig) {
    return Err(dig.error());
  }
  if (!constant_time_equal(dig.value(), verified.digest)) {
    return Err(ErrorCode::FileIntegrityFailed, "file content changed after verification");
  }
  return Ok();
}

} // namespace perceptshift::crypto
