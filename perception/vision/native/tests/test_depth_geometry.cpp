// 去畸变查表与像素过滤。
#include <cmath>

#include "lingtouch/config.h"
#include "lingtouch/perception/cs30_calibration.h"
#include "lingtouch/perception/depth_geometry.h"
#include "test_files.h"
#include "test_harness.h"

using namespace lingtouch;

namespace {

CameraIntrinsics cs30_intrinsics() {
  const auto blob = lt_files::read("cs30/calibration_0.bin");
  return cs30::decode_calibration(blob.data(), blob.size()).value().depth;
}

}  // namespace

LT_TEST(undistortion_table_round_trips) {
  Result<DepthCameraModel> m = DepthCameraModel::create(cs30_intrinsics(), true);
  LT_CHECK_MSG(m, m.error());
  if (!m) return;
  const DepthCameraModel& model = m.value();
  double worst = 0;
  int checked = 0;
  for (int v = 0; v < model.height(); v += 3) {
    for (int u = 0; u < model.width(); u += 3) {
      const size_t i = static_cast<size_t>(v) * model.width() + u;
      if (!model.pixel_valid(i)) continue;
      double pu = 0, pv = 0;
      model.project(model.x(i), model.y(i), &pu, &pv);  // 正向加畸变应回到原像素
      worst = std::fmax(worst, std::fmax(std::fabs(pu - u), std::fabs(pv - v)));
      ++checked;
    }
  }
  const double invalid_fraction = static_cast<double>(model.invalid_pixels()) / (640.0 * 480.0);
  std::printf("  查表回投最大误差 %.2e 像素（%d 个采样点）；超出畸变可逆范围 %.2f%%\n", worst, checked,
              invalid_fraction * 100);
  LT_CHECK(worst < 1e-3);  // 查表存 float，回投误差远小于 1 像素
  LT_CHECK(invalid_fraction > 0.03 && invalid_fraction < 0.10);  // 四角（Python 估算约 6.5%）
  // 角落像素在可逆范围外，中心像素在范围内
  LT_CHECK(!model.pixel_valid(0));
  LT_CHECK(model.pixel_valid(static_cast<size_t>(240) * 640 + 320));

  Result<DepthCameraModel> raw = DepthCameraModel::create(cs30_intrinsics(), false);
  LT_CHECK(raw && raw.value().invalid_pixels() == 0);
}

LT_TEST(value_wrap_and_flying_filters) {
  CameraIntrinsics in;
  in.width = 20;
  in.height = 20;
  in.fx = in.fy = 20;
  in.cx = in.cy = 10;
  in.id = "test";
  Result<DepthCameraModel> m = DepthCameraModel::create(in, false);
  LT_CHECK(m);
  DepthParams p = default_config().value().depth;
  DepthFrame f;
  f.width = 20;
  f.height = 20;
  f.depth_mm.assign(400, 2000);  // 一面平墙
  f.depth_mm[0] = 0;              // 无数据
  f.depth_mm[1] = 1;              // 恰为 1（过曝）
  f.depth_mm[2] = 50;             // 低于最小量程
  f.depth_mm[3] = 7000;           // 超出量程
  // 右下角一块无效区里的孤立近点：疑似相位绕回
  for (int y = 12; y < 20; ++y)
    for (int x = 12; x < 20; ++x) f.depth_mm[y * 20 + x] = 0;
  f.depth_mm[16 * 20 + 16] = 600;
  // 墙中间一个飞点：和所有邻居都差得远
  f.depth_mm[5 * 20 + 5] = 3000;
  DepthMask mask;
  compute_depth_mask(f, m.value(), p, &mask);
  LT_CHECK(!mask.valid[0] && !mask.valid[1] && !mask.valid[2] && !mask.valid[3]);
  LT_CHECK(mask.value_valid == 400 - 4 - 64 + 1);
  LT_CHECK(!mask.valid[16 * 20 + 16]);  // 绕回点被去掉
  LT_CHECK(mask.after_wrap == mask.value_valid - 1);
  LT_CHECK(!mask.valid[5 * 20 + 5]);  // 飞点被去掉
  LT_CHECK(mask.valid[5 * 20 + 6]);   // 旁边的墙面点保留
  // 一条 1 像素宽、深度连续的细线（例如远处的椅腿）在默认偏松参数下保留
  for (int y = 0; y < 10; ++y) f.depth_mm[y * 20 + 9] = 1200;
  compute_depth_mask(f, m.value(), p, &mask);
  int kept = 0;
  for (int y = 1; y < 9; ++y) kept += mask.valid[y * 20 + 9];
  LT_CHECK(kept == 8);
  // 关掉过滤器后都保留
  p.wrap_window_radius_px = 0;
  p.flying_min_consistent_neighbors = 0;
  compute_depth_mask(f, m.value(), p, &mask);
  LT_CHECK(mask.after_flying == mask.value_valid);
}

LT_TEST_MAIN()
