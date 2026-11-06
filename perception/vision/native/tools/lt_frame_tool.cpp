// 主机小工具：对一帧原始深度（640×480 uint16 小端毫米，例如 perception/cs30/reference_000.bin，
// 或 PC 上 independent_proof.py 存下的 depth_NNN.raw）打印 9×6 栅格或平面检查。
//
//   lt_frame_tool grid  <帧文件> <标定 blob> [覆盖参数文件]
//   lt_frame_tool plane <帧文件> <标定 blob>
#include <cstdio>
#include <fstream>
#include <iterator>
#include <string>
#include <vector>

#include "lingtouch/config.h"
#include "lingtouch/perception/cs30_calibration.h"
#include "lingtouch/perception/pipeline.h"
#include "lingtouch/report_json.h"

using namespace lingtouch;

namespace {

bool read_file(const char* path, std::vector<uint8_t>* out) {
  std::ifstream in(path, std::ios::binary);
  if (!in) return false;
  out->assign(std::istreambuf_iterator<char>(in), std::istreambuf_iterator<char>());
  return true;
}

int usage() {
  std::fprintf(stderr,
               "用法：\n  lt_frame_tool grid  <帧文件> <标定 blob> [覆盖参数文件]\n"
               "  lt_frame_tool plane <帧文件> <标定 blob>\n");
  return 2;
}

}  // namespace

int main(int argc, char** argv) {
  if (argc < 4) return usage();
  const std::string mode = argv[1];
  std::vector<uint8_t> raw, blob, overrides;
  if (!read_file(argv[2], &raw) || raw.size() != 640u * 480u * 2u) {
    std::fprintf(stderr, "读不到帧文件，或大小不是 614400 字节：%s\n", argv[2]);
    return 1;
  }
  if (!read_file(argv[3], &blob)) {
    std::fprintf(stderr, "读不到标定 blob：%s\n", argv[3]);
    return 1;
  }
  Result<cs30::Calibration> cal = cs30::decode_calibration(blob.data(), blob.size());
  if (!cal) {
    std::fprintf(stderr, "标定解码失败：%s\n", cal.error().c_str());
    return 1;
  }
  Result<Config> config = default_config();
  if (!config) {
    std::fprintf(stderr, "默认参数有误：%s\n", config.error().c_str());
    return 1;
  }
  if (mode == "grid" && argc >= 5) {
    if (!read_file(argv[4], &overrides)) {
      std::fprintf(stderr, "读不到覆盖参数文件：%s\n", argv[4]);
      return 1;
    }
    config = parse_config(std::string(overrides.begin(), overrides.end()), config.value(), false);
    if (!config) {
      std::fprintf(stderr, "覆盖参数有误：%s\n", config.error().c_str());
      return 1;
    }
  }
  DepthFrame frame;
  frame.width = 640;
  frame.height = 480;
  frame.depth_mm.resize(640 * 480);
  for (size_t i = 0; i < frame.depth_mm.size(); ++i)
    frame.depth_mm[i] = static_cast<uint16_t>(raw[2 * i] | (raw[2 * i + 1] << 8));

  if (mode == "plane") {
    std::printf("%s", format_plane_check(check_planarity(frame, cal.value().depth, config.value().depth, 0.5)).c_str());
    return 0;
  }
  if (mode != "grid") return usage();
  DepthPipeline pipeline(config.value());
  Status s = pipeline.set_intrinsics(cal.value().depth);
  if (!s) {
    std::fprintf(stderr, "内参不可用：%s\n", s.message.c_str());
    return 1;
  }
  const OccupancyGrid g = pipeline.process(frame);
  std::printf("内参 %s\n状态 %s %s\n", cal.value().depth.id.c_str(), grid_status_name(g.status), g.ground.failure.c_str());
  std::printf("像素 %u → 有效值 %u → 去绕回 %u → 去飞点 %u；地面候选 %u、内点 %u；离地 %.3f m，俯仰 %.1f°\n",
              g.counts.pixels, g.counts.value_valid, g.counts.after_wrap, g.counts.after_flying, g.ground.candidates,
              g.ground.inliers, g.ground.height_m, g.ground.pitch_deg);
  std::printf("%s", format_grid(g).c_str());
  std::printf("摘要 %s（与安卓、鸿蒙「核对帧文件」显示的摘要比对）\n", grid_digest(g).c_str());
  return 0;
}
