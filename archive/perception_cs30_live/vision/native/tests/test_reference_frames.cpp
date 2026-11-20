// 3 张真实参考帧（perception/cs30/reference_*.bin，10/25 PC 端抓取）：跑一遍不崩、输出确定、打印栅格。
// 这 3 帧基本是近场（约 40% 像素恰为 1、30–42% 为 0），不用来判断几何对不对。
#include <cstdio>
#include <string>

#include "lingtouch/config.h"
#include "lingtouch/perception/cs30_calibration.h"
#include "lingtouch/perception/pipeline.h"
#include "test_files.h"
#include "test_harness.h"

using namespace lingtouch;

namespace {

bool same(const OccupancyGrid& a, const OccupancyGrid& b) {
  if (a.status != b.status || a.cells != b.cells) return false;
  for (int i = 0; i < kGridCells; ++i) {
    const CellDiagnostics &x = a.diag[i], &y = b.diag[i];
    if (x.band_points != y.band_points || x.ground_points != y.ground_points || x.other_points != y.other_points ||
        x.ground_subblocks_seen != y.ground_subblocks_seen)
      return false;
  }
  const PipelineCounts &p = a.counts, &q = b.counts;
  return p.pixels == q.pixels && p.value_valid == q.value_valid && p.after_wrap == q.after_wrap &&
         p.after_flying == q.after_flying && p.in_grid == q.in_grid && a.ground.ok == b.ground.ok &&
         a.ground.normal == b.ground.normal && a.ground.height_m == b.ground.height_m &&
         a.ground.inliers == b.ground.inliers && a.ground.failure == b.ground.failure;
}

}  // namespace

LT_TEST(reference_frames_are_deterministic) {
  const auto blob = lt_files::read("cs30/calibration_0.bin");
  const CameraIntrinsics in = cs30::decode_calibration(blob.data(), blob.size()).value().depth;
  const Config config = default_config().value();
  const char* names[] = {"cs30/reference_000.bin", "cs30/reference_020.bin",
                         "cs30/reference_040.bin"};
  DepthPipeline shared(config);
  LT_CHECK(shared.set_intrinsics(in));
  OccupancyGrid first[3];
  for (int k = 0; k < 3; ++k) {
    const DepthFrame f = lt_files::read_depth_frame(names[k], static_cast<uint64_t>(k));
    LT_CHECK(f.depth_mm.size() == 640u * 480u);
    first[k] = shared.process(f);
    DepthPipeline fresh(config);
    LT_CHECK(fresh.set_intrinsics(in));
    LT_CHECK_MSG(same(first[k], fresh.process(f)), "新建的流水线结果不同");
    const OccupancyGrid& g = first[k];
    std::printf("  %s：%s（%s）\n", names[k], grid_status_name(g.status), g.ground.failure.c_str());
    std::printf("    像素 %u → 有效值 %u → 去绕回 %u → 去飞点 %u；地面候选 %u、内点 %u；落进栅格 %u\n",
                g.counts.pixels, g.counts.value_valid, g.counts.after_wrap, g.counts.after_flying,
                g.ground.candidates, g.ground.inliers, g.counts.in_grid);
    std::printf("%s", format_grid(g).c_str());
  }
  // 倒序再跑一遍：同一个流水线对象处理过别的帧，结果也不变
  for (int k = 2; k >= 0; --k) {
    const DepthFrame f = lt_files::read_depth_frame(names[k], static_cast<uint64_t>(k));
    LT_CHECK_MSG(same(first[k], shared.process(f)), "处理顺序影响了结果");
  }
}

LT_TEST_MAIN()
