// 地面拟合（第一阶段不用 IMU）：RANSAC 找平面 → 最小二乘精修 → 质量检查。
// 由此得到镜头离地高度和俯仰、横滚；失败时输出原因，上层把整张图置 2。
#pragma once

#include <array>
#include <vector>

#include "lingtouch/config.h"
#include "lingtouch/modules.h"
#include "lingtouch/types.h"

namespace lingtouch {

// 点集的最小二乘平面：返回单位法线和平面方程 normal·P + offset = 0。点少于 3 个时返回 false。
bool fit_plane_least_squares(const std::vector<Point3>& points, std::array<double, 3>* normal, double* offset);

// 拟合地面。candidates 是相机坐标系下的候选点（通常按 sample_stride_px 抽样）。
GroundEstimate fit_ground_plane(const std::vector<Point3>& candidates, const GroundParams& params);

class PlaneFitGroundPose final : public GroundPose {
 public:
  explicit PlaneFitGroundPose(GroundParams params) : params_(params) {}
  GroundEstimate estimate(const std::vector<Point3>& camera_points, const ImuSample* imu) override;

 private:
  GroundParams params_;
};

// 相机坐标 → 地面坐标（x 右、y 前、z 上；原点为相机在地面的垂直投影）。
// ground.ok 必须为 true；image_mirrored 时把 x 取反（深度图本身左右镜像的情况）。
struct GroundFrame {
  std::array<double, 3> right{};
  std::array<double, 3> forward{};
  std::array<double, 3> up{};
  double height = 0;
  bool mirror_x = false;

  GroundPoint to_ground(const Point3& p) const {
    const double x = right[0] * p.x + right[1] * p.y + right[2] * p.z;
    return GroundPoint{mirror_x ? -x : x, forward[0] * p.x + forward[1] * p.y + forward[2] * p.z,
                       up[0] * p.x + up[1] * p.y + up[2] * p.z + height};
  }
};

GroundFrame make_ground_frame(const GroundEstimate& ground, bool image_mirrored);

}  // namespace lingtouch
