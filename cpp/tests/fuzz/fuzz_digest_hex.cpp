#include "perceptshift/crypto/digest.hpp"

#include <cstddef>
#include <cstdint>
#include <string_view>

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
  if (data == nullptr && size != 0) {
    return 0;
  }
  const std::string_view hex(reinterpret_cast<const char*>(data), size);
  (void)perceptshift::crypto::from_hex(hex);
  (void)perceptshift::crypto::sha256_bytes(hex);
  return 0;
}
