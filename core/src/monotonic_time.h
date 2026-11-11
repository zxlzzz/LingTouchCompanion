#pragma once

#include <chrono>
#include <cstdint>

namespace lingtouch {

inline int64_t monotonic_time_ns() {
  return std::chrono::duration_cast<std::chrono::nanoseconds>(
             std::chrono::steady_clock::now().time_since_epoch())
      .count();
}

}  // namespace lingtouch
