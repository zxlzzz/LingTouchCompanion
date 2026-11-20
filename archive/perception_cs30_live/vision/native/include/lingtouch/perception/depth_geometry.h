// 深度图 → 相机坐标点：去畸变查表、无效值与噪声过滤、反投影。
//
// 为了让安卓和鸿蒙对同一帧输出完全一致的结果：只用加减乘除和 sqrt（IEEE 下结果确定），
// 编译时关掉 FMA 合并（见 core/CMakeLists.txt），不依赖平台 libm 的超越函数做判决。
#pragma once

#include <cstddef>
#include <cstdint>
#include <vector>

#include "lingtouch/config.h"
#include "lingtouch/modules.h"
#include "lingtouch/result.h"
#include "lingtouch/types.h"

namespace lingtouch {

// 每个像素去畸变后的归一化坐标，建一次反复用。
// 畸变多项式在大半径处会折返（CS30 的系数在 r≈1.4 处到顶），超出可逆范围的像素
// （CS30 是图像四角，约 6.5%）标为无效，不硬算一条错误的射线。
class DepthCameraModel {
 public:
  static Result<DepthCameraModel> create(const CameraIntrinsics& intrinsics, bool undistort);

  const CameraIntrinsics& intrinsics() const { return intrinsics_; }
  bool undistorted() const { return undistort_; }
  int width() const { return intrinsics_.width; }
  int height() const { return intrinsics_.height; }
  bool pixel_valid(size_t i) const { return valid_[i] != 0; }
  double x(size_t i) const { return x_[i]; }
  double y(size_t i) const { return y_[i]; }
  double inv_norm(size_t i) const { return inv_norm_[i]; }  // 1 / |(x, y, 1)|
  uint32_t invalid_pixels() const { return invalid_pixels_; }

  // 正向模型：归一化坐标 → 像素坐标（加畸变）。测试用它验证查表。
  void project(double xn, double yn, double* u, double* v) const;

 private:
  CameraIntrinsics intrinsics_;
  bool undistort_ = false;
  std::vector<float> x_, y_, inv_norm_;
  std::vector<uint8_t> valid_;
  uint32_t invalid_pixels_ = 0;
};

// 一个像素反投影到相机坐标（x 右、y 下、z 前，米）。
inline Point3 backproject(const DepthCameraModel& m, size_t i, uint16_t depth_mm, DepthMeaning meaning) {
  const double d = static_cast<double>(depth_mm) / 1000.0;
  const double z = meaning == DepthMeaning::kRadialDistance ? d * m.inv_norm(i) : d;
  return Point3{m.x(i) * z, m.y(i) * z, z};
}

struct DepthMask {
  std::vector<uint8_t> valid;
  uint32_t value_valid = 0;
  uint32_t after_wrap = 0;
  uint32_t after_flying = 0;
};

// 依次做：无效值（0、恰为 1、量程外、超出畸变可逆范围）→ 疑似相位绕回的孤立近点 → 边缘飞点。
void compute_depth_mask(const DepthFrame& frame, const DepthCameraModel& model, const DepthParams& params,
                        DepthMask* mask);

}  // namespace lingtouch
