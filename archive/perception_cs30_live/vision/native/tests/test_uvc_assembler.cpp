// 拆帧器：用合成的包流测 FID 翻转、EOF、错误位、空包、坏头、超长与按批传入。
#include <cstring>
#include <vector>

#include "lingtouch/perception/cs30_protocol.h"
#include "lingtouch/perception/uvc_frame_assembler.h"
#include "test_harness.h"

using namespace lingtouch;

namespace {

constexpr uint8_t kEof = 0x02, kErr = 0x40;

struct Collected {
  std::vector<std::vector<uint8_t>> frames;
  UvcFrameAssembler::FrameSink sink() {
    return [this](const uint8_t* d, size_t n) { frames.emplace_back(d, d + n); };
  }
};

std::vector<uint8_t> packet(uint8_t flags, const uint8_t* payload, size_t n, uint8_t header = 2) {
  std::vector<uint8_t> p(header + n, 0);
  p[0] = header;
  p[1] = flags;
  if (n) std::memcpy(p.data() + header, payload, n);
  return p;
}

// 一帧真实布局：200 个 3070 字节负载 + 最后 400 字节（含头 402），共 614400
std::vector<std::vector<uint8_t>> frame_packets(const std::vector<uint8_t>& frame, int fid, bool with_eof) {
  std::vector<std::vector<uint8_t>> out;
  size_t off = 0;
  for (int i = 0; i < 200; ++i, off += 3070) out.push_back(packet(static_cast<uint8_t>(fid), frame.data() + off, 3070));
  out.push_back(packet(static_cast<uint8_t>(fid | (with_eof ? kEof : 0)), frame.data() + off, 400));
  return out;
}

std::vector<uint8_t> make_frame(uint8_t seed) {
  std::vector<uint8_t> f(cs30::kFrameBytes);
  for (size_t i = 0; i < f.size(); ++i) f[i] = static_cast<uint8_t>(i * 31 + seed);
  return f;
}

}  // namespace

LT_TEST(eof_completes_frame) {
  Collected c;
  UvcFrameAssembler a(cs30::kFrameBytes, c.sink());
  const auto f = make_frame(1);
  for (const auto& p : frame_packets(f, 0, true)) a.push_packet(p.data(), p.size());
  LT_CHECK(c.frames.size() == 1);
  LT_CHECK(c.frames.size() == 1 && c.frames[0] == f);
  LT_CHECK(a.stats().frames == 1 && a.stats().incomplete == 0);
}

LT_TEST(fid_toggle_completes_frame_without_eof) {
  Collected c;
  UvcFrameAssembler a(cs30::kFrameBytes, c.sink());
  const auto f0 = make_frame(2), f1 = make_frame(3);
  for (const auto& p : frame_packets(f0, 0, false)) a.push_packet(p.data(), p.size());
  LT_CHECK(c.frames.empty());  // 还没收到 EOF，也没翻转
  for (const auto& p : frame_packets(f1, 1, true)) a.push_packet(p.data(), p.size());
  LT_CHECK(c.frames.size() == 2);
  LT_CHECK(c.frames.size() == 2 && c.frames[0] == f0 && c.frames[1] == f1);
}

LT_TEST(error_bit_drops_current_frame) {
  Collected c;
  UvcFrameAssembler a(cs30::kFrameBytes, c.sink());
  const auto f0 = make_frame(4), f1 = make_frame(5);
  auto pk = frame_packets(f0, 0, true);
  pk[100][1] |= kErr;  // 帧中间出错
  for (const auto& p : pk) a.push_packet(p.data(), p.size());
  LT_CHECK(c.frames.empty());
  LT_CHECK(a.stats().uvc_errors == 1);
  LT_CHECK(a.stats().incomplete == 1);  // 出错后剩下的半帧在 EOF 时按长度不对丢掉
  for (const auto& p : frame_packets(f1, 1, true)) a.push_packet(p.data(), p.size());
  LT_CHECK(c.frames.size() == 1 && c.frames[0] == f1);
}

LT_TEST(empty_and_header_only_packets_are_ignored) {
  Collected c;
  UvcFrameAssembler a(cs30::kFrameBytes, c.sink());
  const auto f = make_frame(6);
  const auto pk = frame_packets(f, 1, true);
  for (size_t i = 0; i < pk.size(); ++i) {
    const auto header_only = packet(1, nullptr, 0);
    a.push_packet(header_only.data(), header_only.size());  // 只有头、没有数据
    a.push_packet(pk[i].data(), pk[i].size());
  }
  // 开流时的空图：只有带 EOF 的头
  const auto empty_eof = packet(static_cast<uint8_t>(0 | kEof), nullptr, 0);
  a.push_packet(empty_eof.data(), empty_eof.size());
  LT_CHECK(c.frames.size() == 1 && c.frames[0] == f);
  LT_CHECK(a.stats().incomplete == 0);
}

LT_TEST(bad_header_and_truncated_frames) {
  Collected c;
  UvcFrameAssembler a(cs30::kFrameBytes, c.sink());
  const uint8_t bad1[] = {1, 0, 9, 9};  // bHeaderLength < 2
  const uint8_t bad2[] = {12, 0, 9, 9};  // bHeaderLength > 包长
  const uint8_t bad3[] = {2};            // 不足 2 字节
  a.push_packet(bad1, sizeof(bad1));
  a.push_packet(bad2, sizeof(bad2));
  a.push_packet(bad3, sizeof(bad3));
  LT_CHECK(a.stats().bad_header == 3);
  auto pk = frame_packets(make_frame(7), 0, true);
  pk.erase(pk.begin() + 50);  // 丢一个包
  for (const auto& p : pk) a.push_packet(p.data(), p.size());
  LT_CHECK(c.frames.empty());
  LT_CHECK(a.stats().incomplete == 1);
  // 超长：多塞一个包
  auto longer = frame_packets(make_frame(8), 1, false);
  longer.push_back(packet(static_cast<uint8_t>(1 | kEof), make_frame(9).data(), 3070));
  for (const auto& p : longer) a.push_packet(p.data(), p.size());
  LT_CHECK(c.frames.empty());
  LT_CHECK(a.stats().overflow == 1);
}

LT_TEST(transfer_batches_use_slot_offsets_and_statuses) {
  Collected c;
  UvcFrameAssembler a(cs30::kFrameBytes, c.sink());
  const auto f = make_frame(10);
  const auto pk = frame_packets(f, 0, true);
  // 按 32 个 3072 字节槽位打包成传输；每个传输里穿插空微帧和一个出错的微帧（之后补发）
  std::vector<uint8_t> buffer;
  std::vector<IsoPacketDesc> descs;
  size_t next = 0;
  int transfers = 0;
  while (next < pk.size()) {
    buffer.assign(32 * cs30::kIsoPacketBytes, 0xEE);
    descs.assign(32, IsoPacketDesc{});
    for (int slot = 0; slot < 32; ++slot) {
      descs[slot].length = cs30::kIsoPacketBytes;
      if (slot % 4 == 3 || next >= pk.size()) continue;  // 空微帧
      std::memcpy(buffer.data() + slot * cs30::kIsoPacketBytes, pk[next].data(), pk[next].size());
      descs[slot].actual_length = static_cast<uint32_t>(pk[next].size());
      ++next;
    }
    a.push_transfer(buffer.data(), buffer.size(), descs.data(), descs.size());
    ++transfers;
  }
  LT_CHECK(c.frames.size() == 1 && c.frames[0] == f);
  LT_CHECK(a.stats().empty_packets > 0);
  // 状态非 0 的微帧不进拼帧
  IsoPacketDesc failed{cs30::kIsoPacketBytes, 100, -71};
  a.push_transfer(buffer.data(), buffer.size(), &failed, 1);
  LT_CHECK(a.stats().packet_errors == 1);
  // 描述越过缓冲：计为错误，不越界读
  IsoPacketDesc oversize{cs30::kIsoPacketBytes, cs30::kIsoPacketBytes + 10, 0};
  a.push_transfer(buffer.data(), 16, &oversize, 1);
  LT_CHECK(a.stats().packet_errors == 2);
  LT_CHECK(transfers > 1);
}

LT_TEST_MAIN()
