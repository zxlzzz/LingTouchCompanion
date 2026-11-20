// 不用异常的返回值：跨 JNI / Node-API 时异常不能穿过边界。
#pragma once

#include <optional>
#include <string>
#include <utility>

namespace lingtouch {

template <typename T>
class Result {
 public:
  static Result success(T value) {
    Result r;
    r.value_ = std::move(value);
    return r;
  }
  static Result failure(std::string message) {
    Result r;
    r.error_ = std::move(message);
    return r;
  }

  bool ok() const { return value_.has_value(); }
  explicit operator bool() const { return ok(); }
  const T& value() const { return *value_; }
  T& value() { return *value_; }
  const std::string& error() const { return error_; }

 private:
  std::optional<T> value_;
  std::string error_;
};

struct Status {
  bool ok = true;
  std::string message;

  static Status success() { return Status{}; }
  static Status failure(std::string m) { return Status{false, std::move(m)}; }
  explicit operator bool() const { return ok; }
};

}  // namespace lingtouch
