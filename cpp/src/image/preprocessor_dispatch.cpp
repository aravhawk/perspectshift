#include "perceptshift/image/preprocessor.hpp"
namespace perceptshift::image {
Result<PreprocessResultMeta> preprocess_to_float_tensor(const ImageView& image,
                                                        const PreprocessConfig& config,
                                                        TensorBuffer& output) {
  if (config.backend == PreprocessBackend::Scalar)
    return preprocess_scalar(image, config, output);
#if defined(__aarch64__) || defined(__ARM_NEON)
  if (config.backend == PreprocessBackend::NeonForced) {
    if (!neon_available()) {
      return Error::make(ErrorCode::InputUnsupported,
                         "NEON preprocess backend forced but unavailable");
    }
    return preprocess_neon(image, config, output);
  }
  if (neon_available())
    return preprocess_neon(image, config, output);
#else
  if (config.backend == PreprocessBackend::NeonForced) {
    return Error::make(ErrorCode::InputUnsupported,
                       "NEON preprocess backend forced but unavailable");
  }
#endif
  auto meta = preprocess_scalar(image, config, output);
  if (meta)
    meta.value().unavailable_reason = "NEON_UNAVAILABLE";
  return meta;
}
} // namespace perceptshift::image
