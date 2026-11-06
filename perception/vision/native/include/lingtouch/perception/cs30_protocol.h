// CS30（USB 2207:0016）免 SDK 取流协议。依据 perception/cs30/REPORT.md 与 startup_sequence.json。
//
// 启动：照抄 SDK 的 41 条类控制请求（表由 tools/gen_startup_sequence.py 从 JSON 生成），
// 每条等上一条完成再发，不加 sleep；接口 1 切到 alt 1 后立刻挂 10 个等时传输；传输挂上之后
// 再发 0xa600、0xa700，处理约 270 ms 事件，再发 0xa300（积分时间）。顺序不能反。
// 停流：取消并排空所有传输 → 接口 1 设 alt 0 → 接口 0 设 alt 0 → release。重开就把整个序列再走一遍。
// 出错：先 release 再重开；还不行再 reset 设备。
//
// 本文件只描述协议和数据，不碰任何 USB 接口：安卓由 cs30_libusb 执行，鸿蒙由 ArkTS
// （usbManager.usbControlTransfer / setInterface / usbSubmitTransfer）按同一张表执行。
#pragma once

#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

#include "lingtouch/result.h"

namespace lingtouch {
namespace cs30 {

constexpr uint16_t kVendorId = 0x2207;
constexpr uint16_t kProductId = 0x0016;
constexpr int kControlInterface = 0;    // VideoControl，中断端点 0x81
constexpr int kStreamingInterface = 1;  // VideoStreaming：alt 0 无端点，alt 1 带等时端点 0x82
constexpr uint8_t kIsoEndpoint = 0x82;
constexpr uint32_t kIsoPacketBytes = 3072;  // wMaxPacketSize 0x1400：1024 字节 × 每微帧 3 次
constexpr uint32_t kControlTimeoutMs = 15000;  // Commit 正常约 2.36 s；最早一次失败就是只给了 2 s
constexpr int kWidth = 640;
constexpr int kHeight = 480;
constexpr size_t kFrameBytes = static_cast<size_t>(kWidth) * kHeight * 2;  // 614400，uint16 小端毫米

enum class StepKind : uint8_t { kControl = 1, kSetAlt = 2, kQueueIso = 3 };

struct Step {
  StepKind kind;
  // kControl：setup 各字段；OUT 请求带 data
  uint8_t request_type;
  uint8_t request;
  uint16_t value;
  uint16_t index;
  uint16_t length;
  const uint8_t* data;
  uint16_t data_length;
  // kSetAlt
  uint8_t interface_number;
  uint8_t alt_setting;
  // kQueueIso：传输个数、每个传输的字节数、每个传输的微帧数、超时
  uint8_t iso_transfers;
  uint32_t iso_transfer_bytes;
  uint16_t iso_packets;
  uint32_t iso_timeout_ms;
  // 这一步完成后、发下一步之前，继续处理事件的时间（只有 0xa700 之后是 270 ms）
  uint32_t settle_ms;

  bool is_in() const { return kind == StepKind::kControl && (request_type & 0x80) != 0; }
};

const Step* startup_steps();
size_t startup_step_count();

// 从启动序列的 IN 响应里收集设备信息和两份标定 blob（各 763 字节，14 片）。
// 分片格式：总长 LE16、累计结束偏移 LE16、本片长度 u8，后面跟数据。
struct DeviceInfo {
  std::vector<uint8_t> subtype;   // GET_CUR 0xcb00
  std::vector<uint8_t> firmware;  // GET_CUR 0xc700
  std::vector<uint8_t> serial;    // GET_CUR 0xc800
  std::vector<uint8_t> calibration[2];  // [0] ← 0xc100，[1] ← 0xc200
  bool calibration_complete[2] = {false, false};
};

class StartupCollector {
 public:
  // step_index 指向 startup_steps() 里的一条 IN 请求；data 是设备实际返回的字节
  Status on_response(size_t step_index, const uint8_t* data, size_t size);
  const DeviceInfo& info() const { return info_; }
  void reset();

 private:
  Status add_slice(int which, const uint8_t* data, size_t size);
  DeviceInfo info_;
  std::vector<uint8_t> covered_[2];
};

// 把设备返回的字节转成可读字符串（去掉结尾的 0，非 ASCII 用 \xNN）。
std::string printable(const std::vector<uint8_t>& bytes);

}  // namespace cs30
}  // namespace lingtouch
