#pragma once

#include "perceptshift/version.hpp"

#include <string>

namespace perceptshift {

struct BuildInfo {
  std::string product_name{kProductName};
  std::string version{kVersionString};
  int major{kVersionMajor};
  int minor{kVersionMinor};
  int patch{kVersionPatch};
  std::string git_commit{kGitCommit};
  std::string compiler;
  std::string cxx_standard{"20"};
  bool has_onnxruntime{false};
  bool has_neon_preprocess{false};
};

[[nodiscard]] BuildInfo current_build_info() noexcept;

} // namespace perceptshift
