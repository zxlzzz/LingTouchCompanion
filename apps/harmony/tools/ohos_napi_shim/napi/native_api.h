#pragma once

// Test-only bridge: run the real addon in Node while reproducing OpenHarmony's
// documented byte-length output from napi_get_typedarray_info. Build the addon
// with this include path before Node headers and with -D__OHOS__.
#include <node_api.h>

inline napi_status lingtouch_test_ohos_typedarray_info(napi_env env, napi_value value,
    napi_typedarray_type* type, size_t* length, void** data, napi_value* buffer, size_t* offset) {
  napi_typedarray_type actual_type;
  size_t elements = 0;
  const auto status = ::napi_get_typedarray_info(env, value, &actual_type, &elements, data, buffer, offset);
  if (status != napi_ok) return status;
  if (type) *type = actual_type;
  size_t width = 1;
  switch (actual_type) {
    case napi_int16_array: case napi_uint16_array: width = 2; break;
    case napi_int32_array: case napi_uint32_array: case napi_float32_array: width = 4; break;
    case napi_float64_array: case napi_bigint64_array: case napi_biguint64_array: width = 8; break;
    default: break;
  }
  if (length) *length = elements * width;
  return napi_ok;
}

#define napi_get_typedarray_info lingtouch_test_ohos_typedarray_info
