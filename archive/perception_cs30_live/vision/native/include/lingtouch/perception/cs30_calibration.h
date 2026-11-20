// CS30 标定 blob（763 字节，protobuf）的无 schema 解码。
//
// 没有厂家 schema，字段含义是按数值推断的（结果里 inferred = true）：
//   字段 1  = 深度内参 fx fy cx cy（4 个 float）
//   字段 2  = 深度畸变 k1 k2 p1 p2 k3（5 个 float，OpenCV 顺序）
//   字段 11 = 序列号字符串
//   字段 15 = RGB 内参与畸变 fx fy cx cy k1 k2 p1 p2 k3（9 个 float）
//   字段 16 = RGB←深度 旋转矩阵（9 个 float，行优先）
//   字段 17 = RGB←深度 平移（3 个 float，推断单位毫米）
// 依据：perception/cs30 里 calibration_0.bin 与 calibration_1.bin 只差字段 1 的 5 个字节，且后者
// 恰好是前者的一半（640×480 与 320×240）；按字段 1、2 算出的横向视场约 100°，与规格书吻合。
// 分辨率从 cx、cy 推断。以后拿到真标定时，用 Config/Engine 的内参覆盖入口替换，不改这里。
#pragma once

#include <array>
#include <cstddef>
#include <cstdint>
#include <string>

#include "lingtouch/result.h"
#include "lingtouch/types.h"

namespace lingtouch {
namespace cs30 {

struct Calibration {
  CameraIntrinsics depth;
  bool has_rgb = false;
  CameraIntrinsics rgb;  // 分辨率未知（width/height = 0）
  std::array<double, 9> rgb_from_depth_rotation{};
  std::array<double, 3> rgb_from_depth_translation{};
  std::string serial;
  uint64_t fnv1a64 = 0;  // blob 的 FNV-1a 64 位散列，用作内参版本号的一部分
};

Result<Calibration> decode_calibration(const uint8_t* blob, size_t size);

}  // namespace cs30
}  // namespace lingtouch
