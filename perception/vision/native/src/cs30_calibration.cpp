#include "lingtouch/perception/cs30_calibration.h"

#include <cmath>
#include <cstdio>
#include <cstring>
#include <map>
#include <vector>

namespace lingtouch {
namespace cs30 {
namespace {

struct Field {
  int wire_type = 0;
  uint64_t varint = 0;
  uint32_t fixed32 = 0;
  const uint8_t* bytes = nullptr;
  size_t length = 0;
};

bool read_varint(const uint8_t* p, size_t n, size_t& i, uint64_t& out) {
  out = 0;
  for (int shift = 0; shift < 64; shift += 7) {
    if (i >= n) return false;
    const uint8_t b = p[i++];
    out |= static_cast<uint64_t>(b & 0x7f) << shift;
    if ((b & 0x80) == 0) return true;
  }
  return false;
}

// 只解析一层；同一字段号出现多次时保留第一次（这些 blob 里没有重复字段）。
bool parse_message(const uint8_t* p, size_t n, std::map<int, Field>& out) {
  size_t i = 0;
  while (i < n) {
    uint64_t key = 0;
    if (!read_varint(p, n, i, key)) return false;
    const int number = static_cast<int>(key >> 3);
    Field f;
    f.wire_type = static_cast<int>(key & 7);
    switch (f.wire_type) {
      case 0:
        if (!read_varint(p, n, i, f.varint)) return false;
        break;
      case 1:
        if (n - i < 8) return false;
        i += 8;
        break;
      case 2: {
        uint64_t len = 0;
        if (!read_varint(p, n, i, len) || len > n - i) return false;
        f.bytes = p + i;
        f.length = static_cast<size_t>(len);
        i += f.length;
        break;
      }
      case 5:
        if (n - i < 4) return false;
        f.fixed32 = static_cast<uint32_t>(p[i]) | (static_cast<uint32_t>(p[i + 1]) << 8) |
                    (static_cast<uint32_t>(p[i + 2]) << 16) | (static_cast<uint32_t>(p[i + 3]) << 24);
        i += 4;
        break;
      default:
        return false;
    }
    if (number > 0) out.emplace(number, f);
  }
  return true;
}

double as_float(uint32_t bits) {
  float f = 0;
  std::memcpy(&f, &bits, sizeof(f));
  return static_cast<double>(f);
}

// 子消息里字段 1..count 都是 fixed32 float
bool read_float_message(const Field& f, size_t count, std::vector<double>& out) {
  if (f.wire_type != 2) return false;
  std::map<int, Field> sub;
  if (!parse_message(f.bytes, f.length, sub)) return false;
  out.assign(count, 0.0);
  for (size_t k = 0; k < count; ++k) {
    auto it = sub.find(static_cast<int>(k) + 1);
    if (it == sub.end() || it->second.wire_type != 5) return false;
    out[k] = as_float(it->second.fixed32);
  }
  return true;
}

// packed repeated float
bool read_packed_floats(const Field& f, size_t count, std::vector<double>& out) {
  if (f.wire_type != 2 || f.length != count * 4) return false;
  out.resize(count);
  for (size_t k = 0; k < count; ++k) {
    const uint8_t* q = f.bytes + 4 * k;
    out[k] = as_float(static_cast<uint32_t>(q[0]) | (static_cast<uint32_t>(q[1]) << 8) |
                      (static_cast<uint32_t>(q[2]) << 16) | (static_cast<uint32_t>(q[3]) << 24));
  }
  return true;
}

bool infer_resolution(double cx, double cy, int& width, int& height) {
  static const int kCandidates[][2] = {{640, 480}, {320, 240}};
  for (const auto& c : kCandidates) {
    if (std::fabs(2 * cx - c[0]) < 0.1 * c[0] && std::fabs(2 * cy - c[1]) < 0.1 * c[1]) {
      width = c[0];
      height = c[1];
      return true;
    }
  }
  return false;
}

uint64_t fnv1a64(const uint8_t* p, size_t n) {
  uint64_t h = 1469598103934665603ULL;
  for (size_t i = 0; i < n; ++i) {
    h ^= p[i];
    h *= 1099511628211ULL;
  }
  return h;
}

}  // namespace

Result<Calibration> decode_calibration(const uint8_t* blob, size_t size) {
  std::map<int, Field> top;
  if (blob == nullptr || size == 0 || !parse_message(blob, size, top))
    return Result<Calibration>::failure("标定数据不是可解析的 protobuf");

  std::vector<double> k;
  std::vector<double> d;
  auto f1 = top.find(1);
  auto f2 = top.find(2);
  if (f1 == top.end() || !read_float_message(f1->second, 4, k))
    return Result<Calibration>::failure("标定数据里没有字段 1（深度内参）");
  if (f2 == top.end() || !read_float_message(f2->second, 5, d))
    return Result<Calibration>::failure("标定数据里没有字段 2（深度畸变）");

  Calibration c;
  CameraIntrinsics& in = c.depth;
  in.fx = k[0];
  in.fy = k[1];
  in.cx = k[2];
  in.cy = k[3];
  in.k1 = d[0];
  in.k2 = d[1];
  in.p1 = d[2];
  in.p2 = d[3];
  in.k3 = d[4];
  in.inferred = true;
  if (!(in.fx > 50 && in.fx < 5000 && in.fy > 50 && in.fy < 5000))
    return Result<Calibration>::failure("焦距不在合理范围，字段含义可能推断错了");
  if (!infer_resolution(in.cx, in.cy, in.width, in.height))
    return Result<Calibration>::failure("从 cx、cy 推断不出分辨率（不是 640×480 或 320×240）");
  for (double v : d)
    if (!(std::fabs(v) < 10)) return Result<Calibration>::failure("畸变系数不在合理范围");

  auto f11 = top.find(11);
  if (f11 != top.end() && f11->second.wire_type == 2)
    c.serial.assign(reinterpret_cast<const char*>(f11->second.bytes), f11->second.length);

  std::vector<double> rgb, rot, trans;
  auto f15 = top.find(15), f16 = top.find(16), f17 = top.find(17);
  if (f15 != top.end() && f16 != top.end() && f17 != top.end() && read_packed_floats(f15->second, 9, rgb) &&
      read_packed_floats(f16->second, 9, rot) && read_packed_floats(f17->second, 3, trans)) {
    c.has_rgb = true;
    c.rgb.fx = rgb[0];
    c.rgb.fy = rgb[1];
    c.rgb.cx = rgb[2];
    c.rgb.cy = rgb[3];
    c.rgb.k1 = rgb[4];
    c.rgb.k2 = rgb[5];
    c.rgb.p1 = rgb[6];
    c.rgb.p2 = rgb[7];
    c.rgb.k3 = rgb[8];
    c.rgb.inferred = true;
    for (int i = 0; i < 9; ++i) c.rgb_from_depth_rotation[i] = rot[i];
    for (int i = 0; i < 3; ++i) c.rgb_from_depth_translation[i] = trans[i];
  }

  c.fnv1a64 = fnv1a64(blob, size);
  char id[160];
  std::snprintf(id, sizeof(id), "cs30:%s:%dx%d:fnv1a64-%016llx:inferred", c.serial.empty() ? "unknown" : c.serial.c_str(),
                in.width, in.height, static_cast<unsigned long long>(c.fnv1a64));
  in.id = id;
  c.rgb.id = in.id + ":rgb";
  return Result<Calibration>::success(c);
}

}  // namespace cs30
}  // namespace lingtouch
