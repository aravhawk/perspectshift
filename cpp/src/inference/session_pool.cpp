#include "perceptshift/inference/session_pool.hpp"

namespace perceptshift::inference {

Result<void> SessionPool::insert(std::string profile_id, std::unique_ptr<OnnxSession> session) {
  std::lock_guard lock(mutex_);
  if (!session) {
    return Err(ErrorCode::InternalInvariantFailed, "null session");
  }
  sessions_[std::move(profile_id)] = std::move(session);
  return Ok();
}

Result<OnnxSession*> SessionPool::get(const std::string& profile_id) {
  std::lock_guard lock(mutex_);
  auto it = sessions_.find(profile_id);
  if (it == sessions_.end()) {
    return Err<OnnxSession*>(ErrorCode::ProfileIncompatible, "session not found for profile");
  }
  return Ok(it->second.get());
}

void SessionPool::erase(const std::string& profile_id) {
  std::lock_guard lock(mutex_);
  sessions_.erase(profile_id);
}

void SessionPool::clear() {
  std::lock_guard lock(mutex_);
  sessions_.clear();
}

std::size_t SessionPool::size() const {
  std::lock_guard lock(mutex_);
  return sessions_.size();
}

} // namespace perceptshift::inference
