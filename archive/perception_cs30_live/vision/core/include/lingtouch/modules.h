// 各模块接口，按《视觉方案 v1.0》第 9 节的模块划分命名。
// 本次实现了 SensorAdapter（CS30）、GroundPose、GeometryGrid、OutputAdapter/TactileEncoder（旧板）；
// 其余只留接口，没有实现，也不提供假实现。
#pragma once

#include <array>
#include <cstdint>
#include <functional>
#include <memory>
#include <string>
#include <vector>

#include "lingtouch/result.h"
#include "lingtouch/tactile.h"
#include "lingtouch/types.h"

namespace lingtouch {

// 相机坐标系下的点：x 右、y 下、z 前（米）。
struct Point3 {
  double x = 0, y = 0, z = 0;
};

// 地面坐标系下的点：x 右、y 前（相机前方在地面的投影）、z 上；原点为相机在地面的垂直投影。
struct GroundPoint {
  double x = 0, y = 0, z = 0;
};

// ---------------------------------------------------------------------------
// SensorAdapter：传感器数据 → 带时间戳和内参的 FrameBundle
// ---------------------------------------------------------------------------
struct FrameBundle {
  DepthFrame depth;
  CameraIntrinsics depth_intrinsics;
  // RGB 与配准以后加；字段先空着，不填假值。
};

class SensorAdapter {
 public:
  virtual ~SensorAdapter() = default;
  using FrameCallback = std::function<void(const FrameBundle&)>;
  virtual Status start(FrameCallback on_frame) = 0;
  virtual void stop() = 0;
};

// ---------------------------------------------------------------------------
// Registration：RGB、深度、外参 → 可关联的像素/点及可见性（仅接口）
// ---------------------------------------------------------------------------
struct RegisteredPixel {
  int depth_u = 0, depth_v = 0;
  double rgb_u = 0, rgb_v = 0;
  bool visible_in_rgb = false;
};

class Registration {
 public:
  virtual ~Registration() = default;
  virtual Result<std::vector<RegisteredPixel>> register_depth_to_rgb(const FrameBundle& frame) = 0;
};

// ---------------------------------------------------------------------------
// GroundPose：深度点、安装参数、可选 IMU → 地面/局部变换/质量
// ---------------------------------------------------------------------------
struct ImuSample {  // 第一阶段不用 IMU，接口先留着
  int64_t time_ns = 0;
  std::array<double, 3> accel{{0, 0, 0}};
  std::array<double, 3> gyro{{0, 0, 0}};
};

class GroundPose {
 public:
  virtual ~GroundPose() = default;
  virtual GroundEstimate estimate(const std::vector<Point3>& camera_points, const ImuSample* imu) = 0;
};

// ---------------------------------------------------------------------------
// GeometryGrid：地面坐标点、可见性 → grid、ground_seen、free_coverage
// ---------------------------------------------------------------------------
class GeometryGrid {
 public:
  virtual ~GeometryGrid() = default;
  // points 已转到地面坐标系；结果写进 grid->cells / grid->diag
  virtual void build(const std::vector<GroundPoint>& points, OccupancyGrid* grid) = 0;
};

// ---------------------------------------------------------------------------
// RGBInstance：RGB → 掩膜、类别分数；配准深度 → 观测点集合（仅接口）
// ---------------------------------------------------------------------------
struct InstanceMask {
  std::string label;
  double class_score = 0;  // 只是类别分数，不是校准过的可信度
  int width = 0, height = 0;
  std::vector<uint8_t> mask;
};

class RGBInstance {
 public:
  virtual ~RGBInstance() = default;
  virtual Result<std::vector<InstanceMask>> segment(const std::vector<uint8_t>& rgb, int width, int height) = 0;
};

// ---------------------------------------------------------------------------
// SpatialLMService：对齐点云、来源快照 → 原始布局和结构候选（仅接口）
// 点云编码器以后要把稀疏卷积改写成"预算邻居表 + 取特征 + 矩阵乘"，本次不做。
// ---------------------------------------------------------------------------
struct LayoutCandidate {
  std::string kind;   // wall / door / window / object
  std::string label;  // 物体类别
  std::array<double, 3> center{{0, 0, 0}};
  std::array<double, 3> size{{0, 0, 0}};
  double yaw = 0;
};

struct SpatialLMRequest {
  uint64_t frame_id = 0;
  int64_t capture_time_ns = 0;
  std::string calibration_id;
  std::vector<Point3> points;  // 已对齐到模型坐标 M
};

class SpatialLMService {
 public:
  virtual ~SpatialLMService() = default;
  virtual Result<std::vector<LayoutCandidate>> analyze(const SpatialLMRequest& request) = 0;
};

// ---------------------------------------------------------------------------
// EvidenceFusion：观测、候选、坐标与时间状态 → 语义信息/独立预测层（仅接口）
// 规则：模型输出只给已经测出来的点团贴类别，不生成、不清除实测格子。
// ---------------------------------------------------------------------------
struct SemanticLayer {
  uint64_t source_frame_id = 0;
  std::vector<LayoutCandidate> supported;  // 有实测点支撑
  std::vector<LayoutCandidate> predicted;  // 无点支撑，只进预测层
};

class EvidenceFusion {
 public:
  virtual ~EvidenceFusion() = default;
  virtual SemanticLayer fuse(const OccupancyGrid& measured, const std::vector<InstanceMask>& masks,
                             const std::vector<LayoutCandidate>& layout) = 0;
};

// ---------------------------------------------------------------------------
// OutputAdapter：实测 grid、质量状态 → GUI、JSON、触觉协议
// ---------------------------------------------------------------------------
class TactileEncoder {
 public:
  virtual ~TactileEncoder() = default;
  // 状态 2 的表示方式必须由调用方显式给出。
  virtual Result<std::vector<uint8_t>> encode(const OccupancyGrid& grid, UnknownCellPolicy policy) const = 0;
};

// 旧板（V2.8 固件，15 字节）编码器。
class LegacyBoardEncoder final : public TactileEncoder {
 public:
  explicit LegacyBoardEncoder(LegacyBoardLayout layout) : layout_(layout) {}
  Result<std::vector<uint8_t>> encode(const OccupancyGrid& grid, UnknownCellPolicy policy) const override {
    Result<LegacyFrame> f = encode_legacy_frame(grid.cells, policy, layout_);
    if (!f) return Result<std::vector<uint8_t>>::failure(f.error());
    return Result<std::vector<uint8_t>>::success(std::vector<uint8_t>(f.value().begin(), f.value().end()));
  }

 private:
  LegacyBoardLayout layout_;
};

class OutputAdapter {
 public:
  virtual ~OutputAdapter() = default;
  virtual void publish(const OccupancyGrid& grid) = 0;
};

}  // namespace lingtouch
