#include <vector>

#include "lingtouch/modules.h"
#include "test_harness.h"

using namespace lingtouch;

namespace {

constexpr uint8_t kPacket[] = {
    0x55, 0x61,
    0x00, 0x40, 0x00, 0xc0, 0x00, 0x80,  // 8, -8, -16 g
    0x00, 0x20, 0x00, 0xe0, 0xff, 0x7f,  // 500, -500, 最大正值
    0x00, 0x40, 0x00, 0xc0, 0xff, 0xff,  // 90, -90, -180/32768 度
};

}  // namespace

LT_TEST(decodes_signed_axes_at_each_packet_split) {
  auto imu = make_wit_ble_imu_adapter();
  std::vector<ImuSample> samples;
  for (size_t split = 1; split < sizeof(kPacket); ++split) {
    samples.clear();
    LT_CHECK(imu->start([&](const ImuSample& s) { samples.push_back(s); }));
    imu->push_notify(kPacket, split, 100);
    LT_CHECK(samples.empty());
    imu->push_notify(kPacket + split, sizeof(kPacket) - split, 200);
    LT_CHECK(samples.size() == 1);
    if (samples.size() != 1) return;
    const auto& s = samples.front();
    LT_CHECK(s.time_ns == 200);
    LT_CHECK(s.accel_g == (std::array<double, 3>{8, -8, -16}));
    LT_CHECK(s.gyro_dps == (std::array<double, 3>{500, -500, 32767.0 * 2000 / 32768}));
    LT_CHECK(s.euler_deg == (std::array<double, 3>{90, -90, -180.0 / 32768}));
    LT_CHECK(!s.has_quat);
  }
}

LT_TEST(resynchronizes_and_emits_multiple_packets_from_one_notify) {
  auto imu = make_wit_ble_imu_adapter();
  std::vector<ImuSample> samples;
  LT_CHECK(imu->start([&](const ImuSample& s) { samples.push_back(s); }));
  const uint8_t reply[20] = {0x55, 0x71, 0x55, 0x61};  // 寄存器数据可能包含测量帧头
  const uint8_t noise[] = {0x00, 0x55, 0x12, 0x55};
  std::vector<uint8_t> notify(noise, noise + sizeof(noise));
  notify.insert(notify.end(), reply, reply + sizeof(reply));
  notify.insert(notify.end(), kPacket, kPacket + sizeof(kPacket));
  notify.insert(notify.end(), kPacket, kPacket + sizeof(kPacket));
  imu->push_notify(notify.data(), notify.size(), 300);
  LT_CHECK(samples.size() == 2);
  for (const auto& s : samples) LT_CHECK(s.time_ns == 300);
}

LT_TEST(stop_discards_partial_packet_and_can_be_called_from_callback) {
  auto imu = make_wit_ble_imu_adapter();
  int count = 0;
  LT_CHECK(!imu->start({}));
  LT_CHECK(imu->start([&](const ImuSample&) { ++count; }));
  imu->push_notify(kPacket, 10, 100);
  imu->stop();
  imu->push_notify(kPacket, sizeof(kPacket), 200);
  LT_CHECK(count == 0);
  LT_CHECK(imu->start([&](const ImuSample&) { ++count; imu->stop(); }));
  imu->push_notify(kPacket + 10, sizeof(kPacket) - 10, 300);
  LT_CHECK(count == 0);
  std::vector<uint8_t> batch(kPacket, kPacket + sizeof(kPacket));
  batch.insert(batch.end(), kPacket, kPacket + sizeof(kPacket));
  imu->push_notify(batch.data(), batch.size(), 400);
  LT_CHECK(count == 1);
}

LT_TEST_MAIN()
