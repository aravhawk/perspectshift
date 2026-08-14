#pragma once

#include <cstddef>
#include <optional>
#include <vector>

namespace perceptshift::util {

template <typename T> class BoundedRing {
public:
  explicit BoundedRing(std::size_t capacity) : buf_(capacity), capacity_(capacity) {}

  [[nodiscard]] std::size_t capacity() const noexcept { return capacity_; }
  [[nodiscard]] std::size_t size() const noexcept { return size_; }
  [[nodiscard]] bool empty() const noexcept { return size_ == 0; }
  [[nodiscard]] bool full() const noexcept { return capacity_ > 0 && size_ == capacity_; }

  // Overwrites oldest when full. Returns true if an element was dropped.
  bool push(T value) {
    if (capacity_ == 0) {
      return true;
    }
    bool dropped = full();
    buf_[head_] = std::move(value);
    head_ = (head_ + 1) % capacity_;
    if (!dropped) {
      ++size_;
    } else {
      tail_ = (tail_ + 1) % capacity_;
    }
    return dropped;
  }

  std::optional<T> pop() {
    if (empty()) {
      return std::nullopt;
    }
    T out = std::move(buf_[tail_]);
    tail_ = (tail_ + 1) % capacity_;
    --size_;
    return out;
  }

  [[nodiscard]] const T* latest() const noexcept {
    if (empty()) {
      return nullptr;
    }
    const std::size_t idx = (head_ + capacity_ - 1) % capacity_;
    return &buf_[idx];
  }

private:
  std::vector<T> buf_;
  std::size_t capacity_{0};
  std::size_t size_{0};
  std::size_t head_{0};
  std::size_t tail_{0};
};

} // namespace perceptshift::util
