#include "perceptshift/build_info.hpp"

namespace perceptshift {

BuildInfo current_build_info() noexcept {
  BuildInfo info;
#if defined(__clang__)
  info.compiler = "clang " __clang_version__;
#elif defined(__GNUC__)
  info.compiler = "gcc";
#else
  info.compiler = "unknown";
#endif
#if defined(PERCEPTSHIFT_HAS_ONNXRUNTIME) && PERCEPTSHIFT_HAS_ONNXRUNTIME
  info.has_onnxruntime = true;
#endif
#if defined(__aarch64__) || defined(__ARM_NEON)
  info.has_neon_preprocess = true;
#endif
  return info;
}

} // namespace perceptshift
