#pragma once

#include "perceptshift/error.hpp"
#include "perceptshift/result.hpp"

#include <cstdint>
#include <limits>

namespace perceptshift::util {

[[nodiscard]] inline Result<std::size_t> checked_mul_size(std::size_t a, std::size_t b) {
  if (a != 0 && b > std::numeric_limits<std::size_t>::max() / a) {
    return Error::make(ErrorCode::ResourceExhausted, "size multiplication overflow");
  }
  return a * b;
}

} // namespace perceptshift::util
