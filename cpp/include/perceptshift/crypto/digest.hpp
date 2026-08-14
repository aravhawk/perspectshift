#pragma once

#include "perceptshift/error.hpp"
#include "perceptshift/result.hpp"

#include <array>
#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <string>
#include <string_view>
#include <vector>

namespace perceptshift::crypto {

using Sha256Digest = std::array<std::uint8_t, 32>;

[[nodiscard]] Result<Sha256Digest> sha256_bytes(const std::uint8_t* data, std::size_t len);
[[nodiscard]] Result<Sha256Digest> sha256_bytes(std::string_view data);
[[nodiscard]] Result<Sha256Digest> sha256_file(const std::string& path);
[[nodiscard]] inline Result<Sha256Digest> sha256_file(const std::filesystem::path& path) {
  return sha256_file(path.string());
}
[[nodiscard]] Result<std::string> sha256_file_hex(const std::filesystem::path& path);
[[nodiscard]] std::string to_hex(const Sha256Digest& digest);
[[nodiscard]] Result<Sha256Digest> from_hex(std::string_view hex);

} // namespace perceptshift::crypto
