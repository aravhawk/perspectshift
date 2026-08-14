#include "perceptshift/runtime/policy_loader.hpp"

#include <cstddef>
#include <cstdint>
#include <nlohmann/json.hpp>

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
  if (data == nullptr || size == 0) {
    return 0;
  }
  try {
    const auto doc = nlohmann::json::parse(data, data + size, nullptr, false);
    if (doc.is_discarded()) {
      return 0;
    }
    (void)perceptshift::runtime::load_runtime_policy_json(doc);
  } catch (...) {
    // Parser / policy loader must not abort the process; exceptions are absorbed for fuzzing.
  }
  return 0;
}
