#include "perceptshift/crypto/digest.hpp"

#include <fstream>
#include <iomanip>
#include <openssl/evp.h>
#include <sstream>
#include <vector>

namespace perceptshift::crypto {
namespace {

Result<Sha256Digest> finalize(EVP_MD_CTX* ctx) {
  Sha256Digest out{};
  unsigned int out_len = 0;
  if (EVP_DigestFinal_ex(ctx, out.data(), &out_len) != 1 || out_len != out.size()) {
    return Error::make(ErrorCode::InternalInvariantFailed, "SHA-256 finalize failed");
  }
  return out;
}

} // namespace

Result<Sha256Digest> sha256_bytes(const std::uint8_t* data, std::size_t len) {
  EVP_MD_CTX* ctx = EVP_MD_CTX_new();
  if (ctx == nullptr) {
    return Error::make(ErrorCode::InternalInvariantFailed, "EVP_MD_CTX_new failed");
  }
  if (EVP_DigestInit_ex(ctx, EVP_sha256(), nullptr) != 1) {
    EVP_MD_CTX_free(ctx);
    return Error::make(ErrorCode::InternalInvariantFailed, "SHA-256 init failed");
  }
  if (len > 0 && EVP_DigestUpdate(ctx, data, len) != 1) {
    EVP_MD_CTX_free(ctx);
    return Error::make(ErrorCode::InternalInvariantFailed, "SHA-256 update failed");
  }
  auto result = finalize(ctx);
  EVP_MD_CTX_free(ctx);
  return result;
}

Result<Sha256Digest> sha256_bytes(std::string_view data) {
  return sha256_bytes(reinterpret_cast<const std::uint8_t*>(data.data()), data.size());
}

Result<Sha256Digest> sha256_file(const std::string& path) {
  std::ifstream in(path, std::ios::binary);
  if (!in) {
    return Error::make(ErrorCode::PathUnsafe, "unable to open file for hashing: " + path,
                       "Check path existence and permissions");
  }
  EVP_MD_CTX* ctx = EVP_MD_CTX_new();
  if (ctx == nullptr) {
    return Error::make(ErrorCode::InternalInvariantFailed, "EVP_MD_CTX_new failed");
  }
  if (EVP_DigestInit_ex(ctx, EVP_sha256(), nullptr) != 1) {
    EVP_MD_CTX_free(ctx);
    return Error::make(ErrorCode::InternalInvariantFailed, "SHA-256 init failed");
  }
  std::vector<char> buf(1 << 16);
  while (in) {
    in.read(buf.data(), static_cast<std::streamsize>(buf.size()));
    const auto got = in.gcount();
    if (got > 0) {
      if (EVP_DigestUpdate(ctx, buf.data(), static_cast<std::size_t>(got)) != 1) {
        EVP_MD_CTX_free(ctx);
        return Error::make(ErrorCode::InternalInvariantFailed, "SHA-256 update failed");
      }
    }
  }
  auto result = finalize(ctx);
  EVP_MD_CTX_free(ctx);
  return result;
}

std::string to_hex(const Sha256Digest& digest) {
  std::ostringstream oss;
  oss << std::hex << std::setfill('0');
  for (auto b : digest) {
    oss << std::setw(2) << static_cast<unsigned>(b);
  }
  return oss.str();
}

Result<Sha256Digest> from_hex(std::string_view hex) {
  if (hex.size() != 64) {
    return Error::make(ErrorCode::ConfigInvalid, "SHA-256 hex must be 64 characters");
  }
  Sha256Digest out{};
  auto nibble = [](char c) -> int {
    if (c >= '0' && c <= '9')
      return c - '0';
    if (c >= 'a' && c <= 'f')
      return c - 'a' + 10;
    if (c >= 'A' && c <= 'F')
      return c - 'A' + 10;
    return -1;
  };
  for (std::size_t i = 0; i < 32; ++i) {
    const int hi = nibble(hex[i * 2]);
    const int lo = nibble(hex[i * 2 + 1]);
    if (hi < 0 || lo < 0) {
      return Error::make(ErrorCode::ConfigInvalid, "invalid hex in digest");
    }
    out[i] = static_cast<std::uint8_t>((hi << 4) | lo);
  }
  return out;
}

Result<std::string> sha256_file_hex(const std::filesystem::path& path) {
  auto dig = sha256_file(path.string());
  if (!dig) {
    return dig.error();
  }
  return to_hex(dig.value());
}

} // namespace perceptshift::crypto
