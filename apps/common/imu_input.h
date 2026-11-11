#pragma once

#include <cstdio>
#include <optional>

#include "../../core/src/monotonic_time.h"
#include "lingtouch/modules.h"

namespace lingtouch {

// App 在其事件线程上驱动同一 BLE 会话。核心解析回调同步返回最新样本。
class ImuInput {
 public:
  Status start() {
    stop();
    return adapter_->start([this](const ImuSample& sample) { latest_ = sample; });
  }

  void stop() {
    adapter_->stop();
    latest_.reset();
  }

  void push(const uint8_t* data, size_t size, int64_t time_ns) {
    adapter_->push_notify(data, size, time_ns);
  }

  std::string latest_text() const {
    if (!latest_) return {};
    const auto& a = latest_->accel_g;
    const auto& w = latest_->gyro_dps;
    const auto& e = latest_->euler_deg;
    char text[160];
    std::snprintf(text, sizeof(text), "加速度 %.2f / %.2f / %.2f g\n角速度 %.2f / %.2f / %.2f °/s\n姿态 %.2f / %.2f / %.2f °",
                  a[0], a[1], a[2], w[0], w[1], w[2], e[0], e[1], e[2]);
    return text;
  }

 private:
  std::unique_ptr<ImuAdapter> adapter_ = make_wit_ble_imu_adapter();
  std::optional<ImuSample> latest_;
};

}  // namespace lingtouch
