#pragma once

#include <cstdint>
#include <optional>
#include <string>
#include <vector>

namespace perceptshift::inference {

enum class ElementType {
  Float32,
  Float16,
  Int8,
  UInt8,
  Int32,
  Int64,
  Bool,
  Unknown,
};

struct TensorSpec {
  std::string name;
  ElementType element_type{ElementType::Float32};
  std::vector<std::int64_t> shape; // -1 = dynamic
  std::string layout;              // nchw/nhwc/raw
};

[[nodiscard]] inline std::string to_string(ElementType t) {
  switch (t) {
  case ElementType::Float32:
    return "float32";
  case ElementType::Float16:
    return "float16";
  case ElementType::Int8:
    return "int8";
  case ElementType::UInt8:
    return "uint8";
  case ElementType::Int32:
    return "int32";
  case ElementType::Int64:
    return "int64";
  case ElementType::Bool:
    return "bool";
  case ElementType::Unknown:
    return "unknown";
  }
  return "unknown";
}

} // namespace perceptshift::inference
