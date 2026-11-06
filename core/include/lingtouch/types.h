// 端侧核心共用的数据类型。不依赖任何平台接口。
#pragma once

#include <array>
#include <cstdint>
#include <string>
#include <vector>

namespace lingtouch {

// ---------------------------------------------------------------------------
// 深度帧
// ---------------------------------------------------------------------------

// 深度值的含义。CS30 是光轴 Z 还是沿视线的径向距离，目前未确认，
// 做成可切换（配置 depth.meaning），真机用平面检查判断。
enum class DepthMeaning : uint8_t { kOpticalAxisZ = 1, kRadialDistance = 2 };

// 相机内参与畸变（OpenCV 径向-切向模型 k1 k2 p1 p2 k3）。
struct CameraIntrinsics {
  int width = 0;
  int height = 0;
  double fx = 0, fy = 0, cx = 0, cy = 0;
  double k1 = 0, k2 = 0, p1 = 0, p2 = 0, k3 = 0;
  // 内参来源与版本，例如 "cs30:HV0130315L0294:blob-sha256-…"；随每一帧结果一起输出。
  std::string id;
  // true = 字段含义是推断出来的（标定 blob 无 schema 解码），不是厂家文档确认的。
  bool inferred = true;
};

struct DepthFrame {
  uint64_t frame_id = 0;
  // 帧拼完时刻，主机单调时钟（纳秒）。
  int64_t capture_time_ns = 0;
  int width = 0;
  int height = 0;
  std::vector<uint16_t> depth_mm;  // 行优先，单位毫米
  std::string intrinsics_id;       // 解析这帧时使用的内参版本
};

// ---------------------------------------------------------------------------
// 9×6 栅格（Hsinlung 定的范围：左右 ±1.8 m，前方 1.0–3.4 m，每格 40 cm）
// ---------------------------------------------------------------------------

constexpr int kGridCols = 9;
constexpr int kGridRows = 6;
constexpr int kGridCells = kGridCols * kGridRows;
constexpr double kCellSizeM = 0.4;
constexpr double kGridXMinM = -1.8;  // 第 0 列左边界（x 向右）
constexpr double kGridYMinM = 1.0;   // 最近一行的近边界（y 向前）
// 判 0 时把每格切成 4×4 个 10 cm 小块
constexpr int kSubblocksPerSide = 4;
constexpr int kSubblocksPerCell = kSubblocksPerSide * kSubblocksPerSide;
constexpr double kSubblockSizeM = kCellSizeM / kSubblocksPerSide;

// 0 = 格内 4×4 小块都看到地面且高度带内无点；1 = 高度带内实测点达到门槛（优先于 0）；
// 2 = 其余一律（看不到、被挡、视野外、无效）。
enum class CellState : uint8_t { kFree = 0, kOccupied = 1, kUnknown = 2 };

// 行号约定与 experiments/chi2027/visionss/frame_converter.py 一致：row 0 最远（3.0–3.4 m），
// row 5 最近（1.0–1.4 m）；col 0 最左（x ∈ [-1.8, -1.4)），以相机朝向为准、未做穿戴镜像。
inline int cell_index(int row, int col) { return row * kGridCols + col; }

struct CellDiagnostics {
  uint32_t band_points = 0;         // 高度带内的实测点
  uint32_t ground_points = 0;       // 地面容差内的点
  uint32_t other_points = 0;        // 低于高度带下限或高于上限、又不算地面的点
  uint8_t ground_subblocks_seen = 0;  // 0–16，有足够地面点的 10 cm 小块数
};

enum class GridStatus : uint8_t {
  kOk = 0,
  kNoFrame = 1,        // 还没有收到帧
  kNoCalibration = 2,  // 没有可用内参
  kGroundFitFailed = 3,  // 地面拟合失败：降级，整张图为 2
};

const char* grid_status_name(GridStatus s);

struct GroundEstimate {
  bool ok = false;
  std::string failure;  // 失败原因（ok 时为空）
  // 相机坐标系（x 右、y 下、z 前）里的地面法线（指向相机一侧，即"上"）和相机离地高度：
  // 点 P 的离地高度 = normal·P + height_m
  std::array<double, 3> normal{{0, 0, 0}};
  double height_m = 0;
  double pitch_deg = 0;  // 仅供显示：光轴相对水平面向下为正
  double roll_deg = 0;   // 仅供显示
  double rms_m = 0;      // 内点到平面的均方根距离
  uint32_t candidates = 0;
  uint32_t inliers = 0;
};

// 各阶段剩下的像素数，便于在界面和报告里看清楚数据丢在哪一步。
struct PipelineCounts {
  uint32_t pixels = 0;
  uint32_t value_valid = 0;    // 去掉 0、恰为 1、小于下限、大于上限、超出畸变模型可逆范围之后
  uint32_t after_wrap = 0;     // 去掉疑似相位绕回的孤立近点之后
  uint32_t after_flying = 0;   // 去掉边缘飞点之后
  uint32_t in_grid = 0;        // 落进 9×6 范围的点
};

struct OccupancyGrid {
  uint64_t source_frame_id = 0;
  int64_t capture_time_ns = 0;
  std::string intrinsics_id;
  GridStatus status = GridStatus::kNoFrame;
  std::array<CellState, kGridCells> cells{};
  std::array<CellDiagnostics, kGridCells> diag{};
  GroundEstimate ground;
  PipelineCounts counts;

  OccupancyGrid() { cells.fill(CellState::kUnknown); }
};

}  // namespace lingtouch
