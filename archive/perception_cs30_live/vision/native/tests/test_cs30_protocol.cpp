// 启动序列表（由 JSON 生成）与 IN 响应收集。
#include <algorithm>
#include <vector>

#include "lingtouch/perception/cs30_protocol.h"
#include "test_files.h"
#include "test_harness.h"

using namespace lingtouch;

LT_TEST(sequence_matches_report) {
  const cs30::Step* s = cs30::startup_steps();
  const size_t n = cs30::startup_step_count();
  LT_CHECK(n == 44);
  int controls = 0, settles = 0;
  for (size_t i = 0; i < n; ++i) {
    if (s[i].kind == cs30::StepKind::kControl) ++controls;
    if (s[i].settle_ms) {
      ++settles;
      LT_CHECK(s[i].value == 0xa700 && s[i].settle_ms == 270);  // REPORT 第 9 步
    }
  }
  LT_CHECK(controls == 41);
  LT_CHECK(settles == 1);
  // 第一条：GET_CUR 0xcb00（子型号）
  LT_CHECK(s[0].request_type == 0xa1 && s[0].request == 0x81 && s[0].value == 0xcb00 && s[0].index == 0x0600);
  LT_CHECK(s[1].kind == cs30::StepKind::kSetAlt && s[1].interface_number == 0 && s[1].alt_setting == 0);
  // 只开深度流的 SET_CUR 0xa100：640、480、类型 02
  const cs30::Step& a100 = s[33];
  LT_CHECK(a100.value == 0xa100 && a100.data_length == 25);
  LT_CHECK(a100.data[5] == 0x80 && a100.data[6] == 0x02 && a100.data[7] == 0xe0 && a100.data[8] == 0x01 &&
           a100.data[9] == 0x02);
  // Commit：数据就是 Probe 返回的 26 字节，帧大小字段 = 614400
  const cs30::Step& commit = s[38];
  LT_CHECK(commit.request_type == 0x21 && commit.value == 0x0200 && commit.index == 0x0001 && commit.length == 26);
  const uint32_t frame_size = commit.data[18] | (commit.data[19] << 8) | (commit.data[20] << 16) |
                              (static_cast<uint32_t>(commit.data[21]) << 24);
  LT_CHECK(frame_size == cs30::kFrameBytes);
  const uint8_t probe_response[26] = {0x01, 0x00, 0x01, 0x01, 0x80, 0xf0, 0xfa, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00,
                                      0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x60, 0x09, 0x00, 0x00, 0x04, 0x00, 0x00};
  LT_CHECK(std::equal(commit.data, commit.data + 26, probe_response));
  // 切到 alt 1 后立刻挂 10 个等时传输，之后才发 0xa600 / 0xa700 / 0xa300
  LT_CHECK(s[39].kind == cs30::StepKind::kSetAlt && s[39].interface_number == 1 && s[39].alt_setting == 1);
  LT_CHECK(s[40].kind == cs30::StepKind::kQueueIso && s[40].iso_transfers == 10 && s[40].iso_transfer_bytes == 98304 &&
           s[40].iso_packets == 32 && s[40].iso_timeout_ms == 5000);
  LT_CHECK(s[40].iso_transfer_bytes == s[40].iso_packets * cs30::kIsoPacketBytes);
  LT_CHECK(s[41].value == 0xa600 && s[42].value == 0xa700 && s[43].value == 0xa300);
  LT_CHECK(s[43].data_length == 2 && s[43].data[0] == 0x37 && s[43].data[1] == 0x01);  // 默认积分时间
}

namespace {

// 按 REPORT 的分片格式把 blob 切成响应：总长 LE16、累计结束偏移 LE16、本片长度 u8、数据（每片最多 55 字节）
std::vector<std::vector<uint8_t>> slice(const std::vector<uint8_t>& blob) {
  std::vector<std::vector<uint8_t>> out;
  for (size_t start = 0; start < blob.size(); start += 55) {
    const size_t n = std::min<size_t>(55, blob.size() - start);
    const size_t end = start + n;
    std::vector<uint8_t> r(60, 0);
    r[0] = static_cast<uint8_t>(blob.size() & 0xff);
    r[1] = static_cast<uint8_t>(blob.size() >> 8);
    r[2] = static_cast<uint8_t>(end & 0xff);
    r[3] = static_cast<uint8_t>(end >> 8);
    r[4] = static_cast<uint8_t>(n);
    std::copy(blob.begin() + static_cast<std::ptrdiff_t>(start), blob.begin() + static_cast<std::ptrdiff_t>(end),
              r.begin() + 5);
    out.push_back(r);
  }
  return out;
}

std::vector<size_t> steps_with_value(uint16_t value) {
  std::vector<size_t> idx;
  for (size_t i = 0; i < cs30::startup_step_count(); ++i)
    if (cs30::startup_steps()[i].is_in() && cs30::startup_steps()[i].value == value) idx.push_back(i);
  return idx;
}

}  // namespace

LT_TEST(collector_reassembles_calibration_slices) {
  const auto blob0 = lt_files::read("cs30/calibration_0.bin");
  const auto blob1 = lt_files::read("cs30/calibration_1.bin");
  LT_CHECK(blob0.size() == 763 && blob1.size() == 763);
  const auto s0 = slice(blob0), s1 = slice(blob1);
  const auto c100 = steps_with_value(0xc100), c200 = steps_with_value(0xc200);
  LT_CHECK(s0.size() == 14 && c100.size() == 14 && c200.size() == 14);
  cs30::StartupCollector collector;
  // 倒序喂，也要拼回原样
  for (size_t k = 0; k < s0.size(); ++k) {
    const size_t j = s0.size() - 1 - k;
    LT_CHECK(collector.on_response(c100[j], s0[j].data(), s0[j].size()));
    LT_CHECK(collector.on_response(c200[j], s1[j].data(), s1[j].size()));
  }
  LT_CHECK(collector.info().calibration_complete[0] && collector.info().calibration_complete[1]);
  LT_CHECK(collector.info().calibration[0] == blob0);
  LT_CHECK(collector.info().calibration[1] == blob1);

  const uint8_t serial[] = {'A', 'B', 'C', 0, 0};
  LT_CHECK(collector.on_response(steps_with_value(0xc800)[0], serial, sizeof(serial)));
  LT_CHECK(cs30::printable(collector.info().serial) == "ABC");
}

LT_TEST(collector_rejects_bad_slices) {
  cs30::StartupCollector collector;
  const size_t step = steps_with_value(0xc100)[0];
  const uint8_t too_short[] = {0xfb, 0x02, 0x10};
  LT_CHECK(!collector.on_response(step, too_short, sizeof(too_short)));
  std::vector<uint8_t> bad(60, 0);
  bad[0] = 10;  // 总长 10
  bad[2] = 20;  // 结束偏移 20 > 总长
  bad[4] = 5;
  LT_CHECK(!collector.on_response(step, bad.data(), bad.size()));
  LT_CHECK(!collector.on_response(1, bad.data(), bad.size()));  // 第 1 步是切换接口，不是 IN 请求
}

LT_TEST_MAIN()
