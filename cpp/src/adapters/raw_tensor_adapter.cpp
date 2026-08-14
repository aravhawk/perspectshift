#include "perceptshift/adapters/raw_tensor_adapter.hpp"
namespace perceptshift::adapters {
Result<NormalizedOutput> RawTensorAdapter::postprocess(const TensorView& output) const {
  if (output.data == nullptr)
    return Error::make(ErrorCode::PostprocessFailed, "null tensor");
  std::size_t count = 1;
  for (auto d : output.shape) {
    if (d <= 0)
      return Error::make(ErrorCode::ModelTensorMismatch, "non-positive tensor dimension");
    count *= static_cast<std::size_t>(d);
  }
  NormalizedOutput out;
  out.task = "raw_tensor";
  out.raw_values.assign(output.data, output.data + count);
  return out;
}
} // namespace perceptshift::adapters
