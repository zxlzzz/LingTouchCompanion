// CS30 等时包 → 614400 字节深度帧的拆帧器。规则照 perception/cs30/REPORT.md「帧格式」：
// - 每个非空包开头是 UVC 头，按 bHeaderLength（第 0 字节）去掉；
// - 按 FID（头第 1 字节 bit0）翻转和 EOF（bit1）把包拼成帧；ERR（bit6）丢掉当前帧；
// - 空微帧丢掉；长度不等于一帧的（含开流头几张空图）丢掉并计数。
// 与 perception/cs30/independent_proof.py 的 Capture.packet()/finish() 逻辑一致。
#pragma once

#include <cstddef>
#include <cstdint>
#include <functional>
#include <vector>

namespace lingtouch {

// 一个等时微帧包的描述。传输缓冲里第 i 个包从 sum(length[0..i)) 处开始（不是按实际长度紧挨着）。
struct IsoPacketDesc {
  uint32_t length = 0;         // 申请的长度（缓冲里的槽位大小）
  uint32_t actual_length = 0;  // 实际收到的长度
  int32_t status = 0;          // 0 = 正常完成
};

struct AssemblerStats {
  uint64_t packets = 0;        // 非空包
  uint64_t empty_packets = 0;  // 状态正常但长度为 0 的微帧
  uint64_t packet_errors = 0;  // 包状态非 0，或描述越过缓冲
  uint64_t bad_header = 0;     // bHeaderLength 不合法
  uint64_t uvc_errors = 0;     // 头里 ERR 位
  uint64_t frames = 0;         // 拼出的完整帧
  uint64_t incomplete = 0;     // 长度不对、被丢掉的非空帧
  uint64_t overflow = 0;       // 其中超长的
};

class UvcFrameAssembler {
 public:
  using FrameSink = std::function<void(const uint8_t* data, size_t size)>;

  UvcFrameAssembler(size_t frame_bytes, FrameSink sink);

  // 一个 UVC 负载包（含头）
  void push_packet(const uint8_t* data, size_t size);
  // 一个等时传输里的一批包（按批传入：鸿蒙 ArkTS 每个传输回调调用一次，不是每包一次）
  void push_transfer(const uint8_t* buffer, size_t buffer_size, const IsoPacketDesc* descs, size_t count);

  const AssemblerStats& stats() const { return stats_; }
  void reset();

 private:
  void finish();

  size_t frame_bytes_;
  FrameSink sink_;
  std::vector<uint8_t> buffer_;
  size_t size_ = 0;
  bool overflow_ = false;
  int fid_ = -1;  // 还没见过包时为 -1
  AssemblerStats stats_;
};

}  // namespace lingtouch
