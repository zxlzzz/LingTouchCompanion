#include "lingtouch/perception/cs30_protocol.h"

#include <algorithm>
#include <cstdio>

namespace lingtouch {
namespace cs30 {
namespace {

constexpr Step control(uint8_t request_type, uint8_t request, uint16_t value, uint16_t index, uint16_t length,
                       const uint8_t* data, uint16_t data_length, uint32_t settle_ms) {
  return Step{StepKind::kControl, request_type, request, value, index, length, data, data_length, 0, 0, 0, 0, 0, 0,
              settle_ms};
}

constexpr Step set_alt(uint8_t interface_number, uint8_t alt_setting) {
  return Step{StepKind::kSetAlt, 0, 0, 0, 0, 0, nullptr, 0, interface_number, alt_setting, 0, 0, 0, 0, 0};
}

constexpr Step queue_iso(uint8_t transfers, uint32_t transfer_bytes, uint16_t packets, uint32_t timeout_ms) {
  return Step{StepKind::kQueueIso, 0, 0, 0, 0, 0, nullptr, 0, 0, 0, transfers, transfer_bytes, packets, timeout_ms, 0};
}

#include "cs30_startup_sequence.inc"

}  // namespace

const Step* startup_steps() { return kStartupSequence; }

size_t startup_step_count() { return sizeof(kStartupSequence) / sizeof(kStartupSequence[0]); }

void StartupCollector::reset() {
  info_ = DeviceInfo{};
  covered_[0].clear();
  covered_[1].clear();
}

Status StartupCollector::on_response(size_t step_index, const uint8_t* data, size_t size) {
  if (step_index >= startup_step_count()) return Status::failure("启动序列步骤号越界");
  const Step& s = startup_steps()[step_index];
  if (!s.is_in()) return Status::failure("这一步不是 IN 请求");
  switch (s.value) {
    case 0xcb00:
      info_.subtype.assign(data, data + size);
      break;
    case 0xc700:
      info_.firmware.assign(data, data + size);
      break;
    case 0xc800:
      info_.serial.assign(data, data + size);
      break;
    case 0xc100:
      return add_slice(0, data, size);
    case 0xc200:
      return add_slice(1, data, size);
    default:
      break;  // UVC Probe 的 GET_MAX / GET_CUR：协议照发，响应不需要保存
  }
  return Status::success();
}

Status StartupCollector::add_slice(int which, const uint8_t* data, size_t size) {
  if (size < 5) return Status::failure("标定分片不足 5 字节");
  const size_t total = static_cast<size_t>(data[0]) | (static_cast<size_t>(data[1]) << 8);
  const size_t end = static_cast<size_t>(data[2]) | (static_cast<size_t>(data[3]) << 8);
  const size_t n = data[4];
  if (total == 0 || n == 0 || n > end || end > total || 5 + n > size) return Status::failure("标定分片头不合法");
  std::vector<uint8_t>& blob = info_.calibration[which];
  std::vector<uint8_t>& covered = covered_[which];
  if (blob.empty()) {
    blob.assign(total, 0);
    covered.assign(total, 0);
  } else if (blob.size() != total) {
    return Status::failure("标定分片的总长前后不一致");
  }
  const size_t start = end - n;
  std::copy(data + 5, data + 5 + n, blob.begin() + static_cast<std::ptrdiff_t>(start));
  std::fill(covered.begin() + static_cast<std::ptrdiff_t>(start), covered.begin() + static_cast<std::ptrdiff_t>(end), 1);
  info_.calibration_complete[which] = std::all_of(covered.begin(), covered.end(), [](uint8_t c) { return c != 0; });
  return Status::success();
}

std::string printable(const std::vector<uint8_t>& bytes) {
  size_t n = bytes.size();
  while (n > 0 && bytes[n - 1] == 0) --n;
  std::string out;
  for (size_t i = 0; i < n; ++i) {
    const uint8_t b = bytes[i];
    if (b >= 0x20 && b < 0x7f) {
      out += static_cast<char>(b);
    } else {
      char buf[5];
      std::snprintf(buf, sizeof(buf), "\\x%02x", b);
      out += buf;
    }
  }
  return out;
}

}  // namespace cs30
}  // namespace lingtouch
