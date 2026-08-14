#pragma once

#include "perceptshift/inference/onnx_session.hpp"
#include "perceptshift/result.hpp"

#include <memory>
#include <mutex>
#include <string>
#include <unordered_map>

namespace perceptshift::inference {

class SessionPool {
public:
  Result<void> insert(std::string profile_id, std::unique_ptr<OnnxSession> session);
  [[nodiscard]] Result<OnnxSession*> get(const std::string& profile_id);
  void erase(const std::string& profile_id);
  void clear();
  [[nodiscard]] std::size_t size() const;

private:
  mutable std::mutex mutex_;
  std::unordered_map<std::string, std::unique_ptr<OnnxSession>> sessions_;
};

} // namespace perceptshift::inference
