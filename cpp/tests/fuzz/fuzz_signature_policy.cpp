#include "perceptshift/bundle/bundle_loader.hpp"

#include <cstddef>
#include <cstdint>
#include <string>

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
  if (data == nullptr && size != 0) {
    return 0;
  }
  const std::string text(reinterpret_cast<const char*>(data), size);
  (void)perceptshift::bundle::parse_signature_policy(text);
  return 0;
}
