#include "perceptshift/image/tensor_buffer.hpp"

// TensorBuffer is header-defined as a float storage helper used by preprocessing.
// This translation unit exists so the build graph remains explicit; no additional
// symbols are required beyond the inline class members.

namespace perceptshift::image {
namespace {
[[maybe_unused]] constexpr int kTensorBufferTuAnchor = 0;
}
} // namespace perceptshift::image
