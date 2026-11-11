#include "lingtouch/modules.h"

#include <mutex>
#include <utility>

namespace lingtouch {
namespace {

constexpr size_t kFrameBytes = 20;
constexpr uint8_t kHeader = 0x55;
constexpr uint8_t kMeasurement = 0x61;
constexpr uint8_t kRegisterReply = 0x71;

double read_axis(const uint8_t* bytes, double scale) {
  const int32_t bits = static_cast<int32_t>(bytes[0]) | (static_cast<int32_t>(bytes[1]) << 8);
  const int32_t raw = bits < 0x8000 ? bits : bits - 0x10000;
  return raw * (scale / 32768.0);
}

class WitBleImuAdapter final : public ImuAdapter {
 public:
  Status start(SampleCallback on_sample) override {
    if (!on_sample) return Status::failure("缺少 IMU 样本回调");
    std::lock_guard<std::recursive_mutex> lock(mutex_);
    callback_ = std::make_shared<SampleCallback>(std::move(on_sample));
    used_ = 0;
    return Status::success();
  }

  void stop() override {
    std::lock_guard<std::recursive_mutex> lock(mutex_);
    callback_.reset();
    used_ = 0;
  }

  void push_notify(const uint8_t* data, size_t size, int64_t host_time_ns) override {
    if (data == nullptr || size == 0) return;
    std::lock_guard<std::recursive_mutex> lock(mutex_);
    const auto callback = callback_;
    if (!callback) return;

    for (size_t i = 0; i < size; ++i) {
      const uint8_t byte = data[i];
      if (used_ == 0 && byte != kHeader) continue;
      if (used_ == 1 && byte != kMeasurement && byte != kRegisterReply) {
        // 两个连续的 55：后一个仍可能是新帧头。
        used_ = byte == kHeader ? 1 : 0;
        continue;
      }
      frame_[used_++] = byte;
      if (used_ != kFrameBytes) continue;
      used_ = 0;
      if (frame_[1] != kMeasurement) continue;

      ImuSample sample;
      // 跨通知时以最后一段到达时刻为准，同一通知内的包共享时刻。
      sample.time_ns = host_time_ns;
      for (size_t axis = 0; axis < 3; ++axis) {
        sample.accel_g[axis] = read_axis(&frame_[2 + axis * 2], 16.0);
        sample.gyro_dps[axis] = read_axis(&frame_[8 + axis * 2], 2000.0);
        sample.euler_deg[axis] = read_axis(&frame_[14 + axis * 2], 180.0);
      }
      (*callback)(sample);
      if (callback_ != callback) return;
    }
  }

 private:
  // 回调在推送线程同步执行，可在回调里 stop；外部 stop 等正在执行的回调退出。
  std::recursive_mutex mutex_;
  std::shared_ptr<SampleCallback> callback_;
  std::array<uint8_t, kFrameBytes> frame_{};
  size_t used_ = 0;
};

}  // namespace

std::unique_ptr<ImuAdapter> make_wit_ble_imu_adapter() {
  return std::make_unique<WitBleImuAdapter>();
}

}  // namespace lingtouch
