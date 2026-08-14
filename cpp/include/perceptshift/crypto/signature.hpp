#pragma once

#include "perceptshift/crypto/digest.hpp"
#include "perceptshift/result.hpp"

#include <string>
#include <vector>

namespace perceptshift::crypto {

[[nodiscard]] Result<std::vector<std::uint8_t>>
ed25519_sign(const std::vector<std::uint8_t>& private_key_32, const std::uint8_t* message,
             std::size_t message_len);

[[nodiscard]] Result<void> ed25519_verify(const std::vector<std::uint8_t>& public_key_32,
                                          const std::uint8_t* message, std::size_t message_len,
                                          const std::vector<std::uint8_t>& signature_64);

} // namespace perceptshift::crypto
