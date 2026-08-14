#pragma once
#include "perceptshift/image/image_view.hpp"
#include "perceptshift/image/preprocess_config.hpp"
#include "perceptshift/image/tensor_buffer.hpp"
#include "perceptshift/result.hpp"

#include <string>
namespace perceptshift::image {
enum class PreprocessImplUsed { Scalar, Neon };
struct PreprocessResultMeta {
  PreprocessImplUsed impl{PreprocessImplUsed::Scalar};
  std::string unavailable_reason;
};
[[nodiscard]] Result<PreprocessResultMeta>
preprocess_to_float_tensor(const ImageView& image, const PreprocessConfig& config,
                           TensorBuffer& output);
[[nodiscard]] Result<PreprocessResultMeta>
preprocess_scalar(const ImageView& image, const PreprocessConfig& config, TensorBuffer& output);
#if defined(__aarch64__) || defined(__ARM_NEON)
[[nodiscard]] Result<PreprocessResultMeta>
preprocess_neon(const ImageView& image, const PreprocessConfig& config, TensorBuffer& output);
#endif
[[nodiscard]] bool neon_available() noexcept;
} // namespace perceptshift::image
