#include "lingtouch/perception/uvc_frame_assembler.h"

#include <cstring>
#include <utility>

namespace lingtouch {
namespace {
constexpr uint8_t kFid = 0x01;
constexpr uint8_t kEof = 0x02;
constexpr uint8_t kErr = 0x40;
}  // namespace

UvcFrameAssembler::UvcFrameAssembler(size_t frame_bytes, FrameSink sink, bool variable_length)
    : frame_bytes_(frame_bytes), sink_(std::move(sink)), buffer_(frame_bytes), variable_length_(variable_length) {}

void UvcFrameAssembler::reset() {
  size_ = 0;
  overflow_ = false;
  damaged_ = false;
  fid_ = -1;
  stats_ = AssemblerStats{};
}

void UvcFrameAssembler::finish() {
  if (!overflow_ && !damaged_ && (variable_length_ ? size_ > 0 : size_ == frame_bytes_)) {
    ++stats_.frames;
    if (sink_) sink_(buffer_.data(), size_);
  } else if (size_ > 0 || overflow_ || damaged_) {
    ++stats_.incomplete;
    if (overflow_) ++stats_.overflow;
  }
  size_ = 0;
  overflow_ = false;
  damaged_ = false;
}

void UvcFrameAssembler::push_packet(const uint8_t* data, size_t size) {
  ++stats_.packets;
  if (size < 2) {
    ++stats_.bad_header;
    damaged_ = true;
    return;
  }
  const size_t header = data[0];
  const uint8_t flags = data[1];
  if (header < 2 || header > size) {
    ++stats_.bad_header;
    damaged_ = true;
    return;
  }
  const int fid = flags & kFid;
  if (fid_ >= 0 && fid_ != fid && (size_ > 0 || overflow_ || damaged_)) finish();
  fid_ = fid;
  if (flags & kErr) {
    ++stats_.uvc_errors;
    damaged_ = true;
    if (flags & kEof) finish();
    return;
  }
  const size_t payload = size - header;
  if (payload > frame_bytes_ - size_) {
    overflow_ = true;
  } else if (payload > 0) {
    std::memcpy(buffer_.data() + size_, data + header, payload);
    size_ += payload;
  }
  if (flags & kEof) finish();
}

void UvcFrameAssembler::push_transfer(const uint8_t* buffer, size_t buffer_size, const IsoPacketDesc* descs,
                                      size_t count) {
  size_t offset = 0;
  for (size_t i = 0; i < count; ++i) {
    const IsoPacketDesc& d = descs[i];
    if (d.status != 0) {
      ++stats_.packet_errors;
      damaged_ = true;
    } else if (d.actual_length == 0) {
      ++stats_.empty_packets;
    } else if (offset > buffer_size || d.actual_length > buffer_size - offset || d.actual_length > d.length) {
      ++stats_.packet_errors;
      damaged_ = true;
    } else {
      push_packet(buffer + offset, d.actual_length);
    }
    offset += d.length;
  }
}

}  // namespace lingtouch
