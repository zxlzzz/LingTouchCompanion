// 各模块接口，按《视觉方案 v1.0》第 9 节的模块划分命名。
// 本次实现了 SensorAdapter（CS30）、GroundPose、GeometryGrid、OutputAdapter/TactileEncoder（旧板）；
// 其余只留接口，没有实现，也不提供假实现。
#pragma once

#include <array>
#include <cstddef>
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
// IMU 用的是 WitMotion BWT901BLECL5.0，BLE 直连手机。
// 上游：App 收到 BLE 通知（特征 0000ffe4-...）后不解析，原样把字节和收到时刻推给 ImuAdapter；
//       解析放在 C++ 核心里，鸿蒙和安卓共用一份。
// 下游：ImuAdapter 每解析出一个默认测量包（0x55 0x61，20 字节）就回调一个 ImuSample，供 GroundPose 用。
// 第一阶段 GroundPose 仍不用 IMU；这里只定接口，没有实现。
struct ImuSample {
  // App 收到这条通知的时刻，主机单调时钟（纳秒），和 DepthFrame::capture_time_ns 同一个钟。
  int64_t time_ns = 0;
  // 以下都在 IMU 自己的坐标轴下，数值按厂家协议换算好，不在这里转到相机坐标。
  std::array<double, 3> accel_g{{0, 0, 0}};      // Ax Ay Az，单位 g
  std::array<double, 3> gyro_dps{{0, 0, 0}};     // Wx Wy Wz，单位 °/s
  std::array<double, 3> euler_deg{{0, 0, 0}};    // Roll Pitch Yaw，单位 °，模块自己融合解算出的姿态
  // 四元数不在默认包里，要另发读寄存器指令才有；没读到时 has_quat = false。
  bool has_quat = false;
  std::array<double, 4> quat{{1, 0, 0, 0}};      // Q0 Q1 Q2 Q3
};

class ImuAdapter {
 public:
  virtual ~ImuAdapter() = default;
  using SampleCallback = std::function<void(const ImuSample&)>;
  virtual Status start(SampleCallback on_sample) = 0;
  virtual void stop() = 0;
  // App 每收到一次 BLE 通知调用一次；data 是通知原始字节，一次可能不止一个包，也可能被拆开。
  virtual void push_notify(const uint8_t* data, size_t size, int64_t host_time_ns) = 0;
};

// 要开发的就是这个：返回一个解析 BWT901BLECL5.0 BLE 默认测量包的 ImuAdapter。尚未实现。
// 用 IMU 的一方：adapter = make_wit_ble_imu_adapter(); adapter->start(回调); App 收到通知就 adapter->push_notify(...)。
std::unique_ptr<ImuAdapter> make_wit_ble_imu_adapter();

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
