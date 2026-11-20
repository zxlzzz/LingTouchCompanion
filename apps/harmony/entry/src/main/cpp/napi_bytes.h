#pragma once

#include "napi/native_api.h"
#include <cstdint>
#include <limits>

// OpenHarmony's napi_get_typedarray_info reports bytes, while Node reports
// elements. Keep this difference in one place and validate the backing buffer
// before handing a view to either capture bridge.
inline bool lingtouch_napi_bytes(napi_env env, napi_value value, const uint8_t** data, size_t* size) {
  bool is_buffer = false;
  if (napi_is_arraybuffer(env, value, &is_buffer) != napi_ok) return false;
  void* pointer = nullptr;
  if (is_buffer) {
    if (napi_get_arraybuffer_info(env, value, &pointer, size) != napi_ok) return false;
    *data = static_cast<const uint8_t*>(pointer);
    return *size == 0 || pointer != nullptr;
  }
  bool is_typed = false;
  if (napi_is_typedarray(env, value, &is_typed) != napi_ok || !is_typed) return false;
  napi_typedarray_type type;
  napi_value backing;
  size_t reported = 0, offset = 0;
  if (napi_get_typedarray_info(env, value, &type, &reported, &pointer, &backing, &offset) != napi_ok) return false;
  size_t width = 0;
  switch (type) {
    case napi_int8_array: case napi_uint8_array: case napi_uint8_clamped_array: width = 1; break;
    case napi_int16_array: case napi_uint16_array: width = 2; break;
    case napi_int32_array: case napi_uint32_array: case napi_float32_array: width = 4; break;
    case napi_float64_array: case napi_bigint64_array: case napi_biguint64_array: width = 8; break;
    default: return false;
  }
#ifdef __OHOS__
  const size_t bytes = reported;
#else
  if (reported > std::numeric_limits<size_t>::max() / width) return false;
  const size_t bytes = reported * width;
#endif
  void* backing_data = nullptr;
  size_t capacity = 0;
  if (napi_get_arraybuffer_info(env, backing, &backing_data, &capacity) != napi_ok ||
      offset > capacity || bytes > capacity - offset || bytes % width != 0 ||
      (bytes != 0 && (pointer == nullptr || backing_data == nullptr))) return false;
  *data = static_cast<const uint8_t*>(pointer);
  *size = bytes;
  return true;
}
