#pragma once
#include "napi/native_api.h"
#include "lingtouch/engine.h"
#include <functional>
#include <memory>
void register_camera_api(napi_env env,napi_value exports,
    std::function<std::shared_ptr<lingtouch::Engine>()> get_engine);
