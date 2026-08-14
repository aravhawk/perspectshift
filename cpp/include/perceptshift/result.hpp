#pragma once

#include "perceptshift/error.hpp"

#include <utility>
#include <variant>

namespace perceptshift {

template <typename T> class Result {
public:
  Result(T value) : storage_(std::move(value)) {}
  Result(Error error) : storage_(std::move(error)) {}

  [[nodiscard]] bool ok() const noexcept { return std::holds_alternative<T>(storage_); }
  [[nodiscard]] explicit operator bool() const noexcept { return ok(); }

  [[nodiscard]] T& value() & { return std::get<T>(storage_); }
  [[nodiscard]] const T& value() const& { return std::get<T>(storage_); }
  [[nodiscard]] T&& value() && { return std::get<T>(std::move(storage_)); }

  [[nodiscard]] Error& error() & { return std::get<Error>(storage_); }
  [[nodiscard]] const Error& error() const& { return std::get<Error>(storage_); }

  template <typename U> [[nodiscard]] Result<U> map(U (*fn)(const T&)) const {
    if (!ok()) {
      return error();
    }
    return fn(value());
  }

private:
  std::variant<T, Error> storage_;
};

template <> class Result<void> {
public:
  Result() : ok_(true) {}
  Result(Error error) : ok_(false), error_(std::move(error)) {}

  [[nodiscard]] bool ok() const noexcept { return ok_; }
  [[nodiscard]] explicit operator bool() const noexcept { return ok(); }
  [[nodiscard]] const Error& error() const& { return error_; }
  [[nodiscard]] Error& error() & { return error_; }

  static Result success() { return Result(); }

private:
  bool ok_{false};
  Error error_{};
};

template <typename T> [[nodiscard]] inline Result<T> Ok(T value) {
  return Result<T>(std::move(value));
}

[[nodiscard]] inline Result<void> Ok() {
  return Result<void>::success();
}

template <typename T = void> [[nodiscard]] inline Result<T> Err(Error error) {
  return Result<T>(std::move(error));
}

template <typename T = void>
[[nodiscard]] inline Result<T> Err(ErrorCode code, std::string message,
                                   std::string remediation = {}) {
  return Result<T>(Error::make(code, std::move(message), std::move(remediation)));
}

} // namespace perceptshift
