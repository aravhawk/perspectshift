#pragma once

#include <utility>

namespace perceptshift::util {

template <typename F> class ScopeExit {
public:
  explicit ScopeExit(F&& fn) : fn_(std::forward<F>(fn)), active_(true) {}
  ~ScopeExit() {
    if (active_) {
      fn_();
    }
  }
  ScopeExit(const ScopeExit&) = delete;
  ScopeExit& operator=(const ScopeExit&) = delete;
  ScopeExit(ScopeExit&& other) noexcept : fn_(std::move(other.fn_)), active_(other.active_) {
    other.active_ = false;
  }
  void release() noexcept { active_ = false; }

private:
  F fn_;
  bool active_;
};

template <typename F> [[nodiscard]] ScopeExit<F> scope_exit(F&& fn) {
  return ScopeExit<F>(std::forward<F>(fn));
}

} // namespace perceptshift::util
