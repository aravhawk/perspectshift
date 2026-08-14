#include "perceptshift/util/file_security.hpp"

#include <cstddef>
#include <cstdint>
#include <filesystem>
#include <string>

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
  if (data == nullptr && size != 0) {
    return 0;
  }
  const std::string rel(reinterpret_cast<const char*>(data), size);
  const std::filesystem::path root{"/tmp/perceptshift-fuzz-root"};
  (void)perceptshift::util::ensure_within_root(root, root / rel);
  return 0;
}
