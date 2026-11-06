// 几何正确性：合成场景（已知高度的地面 + 已知位置的物体），断言 0/1/2。
// 内参用 perception/cs30/calibration_0.bin 解出来的那组（含真实的强桶形畸变）。
#include <cmath>
#include <cstdio>
#include <string>

#include "lingtouch/config.h"
#include "lingtouch/perception/cs30_calibration.h"
#include "lingtouch/perception/pipeline.h"
#include "synthetic_scene.h"
#include "test_files.h"
#include "test_harness.h"

using namespace lingtouch;

namespace {

CameraIntrinsics cs30_intrinsics() {
  const auto blob = lt_files::read("cs30/calibration_0.bin");
  return cs30::decode_calibration(blob.data(), blob.size()).value().depth;
}

Config config_with(DepthMeaning meaning) {
  Config c = default_config().value();
  c.depth.meaning = meaning;
  return c;
}

OccupancyGrid run(const lt_synth::Scene& scene, const lt_synth::Pose& pose, DepthMeaning render_as,
                  const Config& config) {
  const CameraIntrinsics in = cs30_intrinsics();
  DepthCameraModel model = DepthCameraModel::create(in, true).value();
  const DepthFrame frame = lt_synth::render(scene, model, pose, render_as);
  DepthPipeline pipeline(config);
  LT_CHECK(pipeline.set_intrinsics(in));
  return pipeline.process(frame);
}

CellState at(const OccupancyGrid& g, int row, int col) { return g.cells[cell_index(row, col)]; }

void print(const char* title, const OccupancyGrid& g) {
  std::printf("  %s：%s，离地 %.3f m，俯仰 %.2f°，横滚 %.2f°，地面内点 %u/%u，%s\n", title, grid_status_name(g.status),
              g.ground.height_m, g.ground.pitch_deg, g.ground.roll_deg, g.ground.inliers, g.ground.candidates,
              g.ground.failure.c_str());
  const std::string text = format_grid(g);
  size_t start = 0;
  for (int r = 0; r < kGridRows; ++r) {
    const size_t end = text.find('\n', start);
    std::printf("    row %d (%.1f–%.1f m)  %s\n", r, kGridYMinM + (kGridRows - 1 - r) * kCellSizeM,
                kGridYMinM + (kGridRows - r) * kCellSizeM, text.substr(start, end - start).c_str());
    start = end + 1;
  }
}

// 箱子 0.3×0.3×0.5 m，放在第 4 列（x ∈ [-0.2, 0.2)）、row 3（y ∈ [1.8, 2.2)）
lt_synth::Scene floor_and_box() {
  lt_synth::Scene s;
  s.boxes.push_back({-0.15, 0.15, 1.85, 2.15, 0.0, 0.5});
  return s;
}

void check_floor_box(const OccupancyGrid& g, const lt_synth::Pose& pose) {
  LT_CHECK(g.status == GridStatus::kOk);
  LT_CHECK_NEAR(g.ground.height_m, pose.height_m, 0.01);
  LT_CHECK_NEAR(g.ground.pitch_deg, pose.pitch_deg, 0.5);
  LT_CHECK(at(g, 3, 4) == CellState::kOccupied);  // 箱子所在格
  LT_CHECK(at(g, 2, 4) == CellState::kUnknown);   // 箱子身后被挡
  LT_CHECK(at(g, 4, 2) == CellState::kFree);      // 看全地板
  LT_CHECK(at(g, 4, 6) == CellState::kFree);
  // 规则自洽：没有点在高度带里的格子，只有 16 个小块都看到地面才是 0
  for (int i = 0; i < kGridCells; ++i) {
    if (g.cells[i] == CellState::kFree) LT_CHECK(g.diag[i].ground_subblocks_seen == kSubblocksPerCell);
    if (g.cells[i] == CellState::kOccupied) LT_CHECK(g.diag[i].band_points >= 5);
  }
}

}  // namespace

LT_TEST(floor_box_optical_z) {
  const lt_synth::Pose pose{1.5, 30, 0};
  const OccupancyGrid g = run(floor_and_box(), pose, DepthMeaning::kOpticalAxisZ, config_with(DepthMeaning::kOpticalAxisZ));
  print("地面+箱子（光轴 Z）", g);
  check_floor_box(g, pose);
}

LT_TEST(floor_box_radial) {
  const lt_synth::Pose pose{1.5, 30, 0};
  const OccupancyGrid g =
      run(floor_and_box(), pose, DepthMeaning::kRadialDistance, config_with(DepthMeaning::kRadialDistance));
  print("地面+箱子（径向距离）", g);
  check_floor_box(g, pose);
}

LT_TEST(roll_and_other_height) {
  const lt_synth::Pose pose{1.7, 40, 6};
  const OccupancyGrid g = run(floor_and_box(), pose, DepthMeaning::kOpticalAxisZ, config_with(DepthMeaning::kOpticalAxisZ));
  print("地面+箱子（高 1.7 m、俯仰 40°、横滚 6°）", g);
  LT_CHECK(g.status == GridStatus::kOk);
  LT_CHECK_NEAR(g.ground.height_m, 1.7, 0.01);
  LT_CHECK_NEAR(g.ground.pitch_deg, 40, 0.5);
  LT_CHECK_NEAR(std::fabs(g.ground.roll_deg), 6, 0.5);
  LT_CHECK(at(g, 3, 4) == CellState::kOccupied);
  LT_CHECK(at(g, 2, 4) == CellState::kUnknown);
}

LT_TEST(thin_leg_survives_default_filter) {
  lt_synth::Scene s;
  s.cylinders.push_back({0.8, 2.0, 0.015, 0.0, 0.8});  // 直径 3 cm 的竖杆，第 6 列、row 3
  const OccupancyGrid g = run(s, {1.5, 30, 0}, DepthMeaning::kOpticalAxisZ, config_with(DepthMeaning::kOpticalAxisZ));
  print("细杆（直径 3 cm）", g);
  LT_CHECK(at(g, 3, 6) == CellState::kOccupied);
}

LT_TEST(objects_outside_height_band) {
  lt_synth::Scene s;
  s.boxes.push_back({-1.0, -0.6, 1.4, 1.8, 0.0, 0.05});  // 5 cm 高的扁盒子：低于高度带下限 0.10 m
  s.boxes.push_back({0.6, 1.0, 1.4, 1.8, 2.0, 2.2});     // 悬在 2.0–2.2 m：高于上限 1.90 m
  const OccupancyGrid g = run(s, {1.5, 30, 0}, DepthMeaning::kOpticalAxisZ, config_with(DepthMeaning::kOpticalAxisZ));
  print("高度带外的物体", g);
  LT_CHECK(g.status == GridStatus::kOk);
  LT_CHECK(at(g, 4, 2) != CellState::kOccupied);
  LT_CHECK(at(g, 4, 6) != CellState::kOccupied);
}

LT_TEST(no_ground_degrades_to_all_unknown) {
  lt_synth::Scene s;
  s.ground = false;
  s.boxes.push_back({-3, 3, 1.2, 1.4, -1, 3});  // 正前方 1.2 m 一面墙，看不到地面
  const OccupancyGrid g = run(s, {1.5, 0, 0}, DepthMeaning::kOpticalAxisZ, config_with(DepthMeaning::kOpticalAxisZ));
  print("看不到地面", g);
  LT_CHECK(g.status == GridStatus::kGroundFitFailed);
  LT_CHECK(!g.ground.failure.empty());
  for (CellState c : g.cells) LT_CHECK(c == CellState::kUnknown);
}

namespace {

const PlaneHypothesis* find(const PlaneCheckReport& r, DepthMeaning meaning, bool undistort) {
  for (const PlaneHypothesis& h : r.hypotheses)
    if (h.meaning == meaning && h.undistort == undistort) return &h;
  return nullptr;
}

DepthMeaning other(DepthMeaning m) {
  return m == DepthMeaning::kOpticalAxisZ ? DepthMeaning::kRadialDistance : DepthMeaning::kOpticalAxisZ;
}

}  // namespace

// 正对墙：能区分光轴 Z 和径向距离；但光轴 Z 时整面墙 Z 相同，去不去畸变都一样平，
// 所以正对墙判断不了要不要去畸变。
LT_TEST(plane_check_frontal_wall_identifies_depth_meaning) {
  const CameraIntrinsics in = cs30_intrinsics();
  DepthCameraModel model = DepthCameraModel::create(in, true).value();
  lt_synth::Scene wall;
  wall.ground = false;
  wall.boxes.push_back({-5, 5, 1.5, 1.6, -5, 5});  // 相机正对 1.5 m 外的墙
  const DepthParams depth = default_config().value().depth;
  for (DepthMeaning truth : {DepthMeaning::kOpticalAxisZ, DepthMeaning::kRadialDistance}) {
    const DepthFrame f = lt_synth::render(wall, model, {1.0, 0, 0}, truth);
    const PlaneCheckReport report = check_planarity(f, in, depth, 0.6);
    std::printf("%s", format_plane_check(report).c_str());
    LT_CHECK(!report.hypotheses.empty() && report.hypotheses[0].ok);
    if (report.hypotheses.empty()) continue;
    LT_CHECK(report.hypotheses[0].meaning == truth);
    LT_CHECK_NEAR(report.hypotheses[0].distance_m, 1.5, 0.01);
    LT_CHECK(report.hypotheses[0].rms_mm < 1.0);  // 只剩毫米取整误差
    for (bool undistort : {true, false}) {
      const PlaneHypothesis* wrong = find(report, other(truth), undistort);
      LT_CHECK(wrong != nullptr && wrong->rms_mm > 5.0);  // 含义错了，墙会弯
    }
  }
}

// 斜着看平面（这里用地面，俯仰 45°）：同时能判断要不要去畸变。
LT_TEST(plane_check_oblique_plane_identifies_undistortion) {
  const CameraIntrinsics in = cs30_intrinsics();
  DepthCameraModel model = DepthCameraModel::create(in, true).value();
  lt_synth::Scene floor;
  const DepthParams depth = default_config().value().depth;
  for (DepthMeaning truth : {DepthMeaning::kOpticalAxisZ, DepthMeaning::kRadialDistance}) {
    const DepthFrame f = lt_synth::render(floor, model, {1.0, 45, 0}, truth);
    const PlaneCheckReport report = check_planarity(f, in, depth, 0.6);
    std::printf("%s", format_plane_check(report).c_str());
    LT_CHECK(!report.hypotheses.empty() && report.hypotheses[0].ok);
    if (report.hypotheses.empty()) continue;
    LT_CHECK(report.hypotheses[0].meaning == truth && report.hypotheses[0].undistort);
    LT_CHECK(report.hypotheses[0].rms_mm < 1.0);
    const PlaneHypothesis* no_undistort = find(report, truth, false);
    LT_CHECK(no_undistort != nullptr && no_undistort->rms_mm > 5.0);
  }
}

LT_TEST_MAIN()
