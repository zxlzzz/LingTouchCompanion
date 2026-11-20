// 深度帧 → 9×6 栅格：过滤 → 反投影 → 地面拟合 → 地面坐标 → 高度带 → 0/1/2。
// 纯计算、无线程、无平台依赖；同一帧、同一参数、同一内参，输出逐字节相同。
#pragma once

#include <optional>
#include <string>
#include <vector>

#include "lingtouch/config.h"
#include "lingtouch/perception/depth_geometry.h"
#include "lingtouch/perception/occupancy.h"
#include "lingtouch/result.h"
#include "lingtouch/types.h"

namespace lingtouch {

class DepthPipeline {
 public:
  explicit DepthPipeline(const Config& config);

  // 换内参（会重建去畸变查表）。
  Status set_intrinsics(const CameraIntrinsics& intrinsics);
  bool has_intrinsics() const { return model_.has_value(); }
  const Config& config() const { return config_; }

  OccupancyGrid process(const DepthFrame& frame);

 private:
  Config config_;
  std::optional<DepthCameraModel> model_;
  OccupancyGridBuilder builder_;
  DepthMask mask_;
  std::vector<Point3> points_;
  std::vector<Point3> candidates_;
  std::vector<GroundPoint> ground_points_;
};

// ---------------------------------------------------------------------------
// 平面检查：判断深度是光轴 Z 还是径向距离、要不要去畸变（真机对着平整的墙拍一帧）。
// 在图像中央区域里，对 4 种组合各做一次最小二乘平面拟合，比较残差：
// 假设对了，墙是平的；假设错了，墙会弯（径向当 Z 用时中间凸出、四周后退）。
// ---------------------------------------------------------------------------
struct PlaneHypothesis {
  DepthMeaning meaning = DepthMeaning::kOpticalAxisZ;
  bool undistort = true;
  bool ok = false;
  std::string failure;
  uint32_t points = 0;
  double rms_mm = 0;
  double p95_mm = 0;
  double distance_m = 0;  // 相机到平面的距离
};

struct PlaneCheckReport {
  double roi_fraction = 0;  // 中央区域占宽、高的比例
  std::vector<PlaneHypothesis> hypotheses;  // 按 rms_mm 从小到大
};

PlaneCheckReport check_planarity(const DepthFrame& frame, const CameraIntrinsics& intrinsics, const DepthParams& depth,
                                 double roi_fraction);

std::string format_plane_check(const PlaneCheckReport& report);

// 9×6 栅格画成 6 行文字（'0' '1' '2'），row 0（最远）在最上面。
std::string format_grid(const OccupancyGrid& grid);

}  // namespace lingtouch
