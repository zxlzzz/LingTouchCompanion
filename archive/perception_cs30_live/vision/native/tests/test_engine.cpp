// 端到端（主机）：启动序列 IN 响应 → 标定 → 合成的等时包流 → 拆帧 → 后台算栅格 → 15 字节旧板帧。
// 等时包是把合成深度帧按 CS30 的包格式切出来的，不是真机数据。
#include <algorithm>
#include <chrono>
#include <cstring>
#include <thread>
#include <vector>

#include "lingtouch/config.h"
#include "lingtouch/engine.h"
#include "lingtouch/perception/cs30_calibration.h"
#include "lingtouch/perception/pipeline.h"
#include "lingtouch/report_json.h"
#include "synthetic_scene.h"
#include "test_files.h"
#include "test_harness.h"

using namespace lingtouch;

namespace {

std::vector<std::vector<uint8_t>> slices(const std::vector<uint8_t>& blob) {
  std::vector<std::vector<uint8_t>> out;
  for (size_t start = 0; start < blob.size(); start += 55) {
    const size_t n = std::min<size_t>(55, blob.size() - start), end = start + n;
    std::vector<uint8_t> r(60, 0);
    r[0] = static_cast<uint8_t>(blob.size() & 0xff);
    r[1] = static_cast<uint8_t>(blob.size() >> 8);
    r[2] = static_cast<uint8_t>(end & 0xff);
    r[3] = static_cast<uint8_t>(end >> 8);
    r[4] = static_cast<uint8_t>(n);
    std::copy(blob.begin() + static_cast<std::ptrdiff_t>(start), blob.begin() + static_cast<std::ptrdiff_t>(end),
              r.begin() + 5);
    out.push_back(r);
  }
  return out;
}

// 深度帧 → 按 CS30 布局切成 3072 字节槽位的等时传输（每个 32 个微帧，含 UVC 头与 FID/EOF）
void push_frame(Engine& engine, const DepthFrame& f, int fid) {
  std::vector<uint8_t> bytes(f.depth_mm.size() * 2);
  for (size_t i = 0; i < f.depth_mm.size(); ++i) {
    bytes[2 * i] = static_cast<uint8_t>(f.depth_mm[i] & 0xff);
    bytes[2 * i + 1] = static_cast<uint8_t>(f.depth_mm[i] >> 8);
  }
  std::vector<uint8_t> buffer(32 * cs30::kIsoPacketBytes);
  std::vector<IsoPacketDesc> descs(32);
  size_t off = 0;
  while (off < bytes.size()) {
    std::fill(buffer.begin(), buffer.end(), 0);
    for (int slot = 0; slot < 32; ++slot) {
      descs[slot] = IsoPacketDesc{cs30::kIsoPacketBytes, 0, 0};
      if (off >= bytes.size()) continue;
      const size_t n = std::min<size_t>(3070, bytes.size() - off);
      uint8_t* p = buffer.data() + slot * cs30::kIsoPacketBytes;
      p[0] = 2;
      p[1] = static_cast<uint8_t>(fid | (off + n == bytes.size() ? 0x02 : 0));
      std::memcpy(p + 2, bytes.data() + off, n);
      descs[slot].actual_length = static_cast<uint32_t>(n + 2);
      off += n;
    }
    engine.push_iso_transfer(buffer.data(), buffer.size(), descs.data(), descs.size());
  }
}

bool wait_for_frame(const Engine& engine, uint64_t frame_id, OccupancyGrid* out) {
  for (int i = 0; i < 500; ++i) {
    const OccupancyGrid g = engine.latest_grid();
    if (g.status != GridStatus::kNoFrame && g.source_frame_id == frame_id) {
      *out = g;
      return true;
    }
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }
  return false;
}

}  // namespace

LT_TEST(startup_packets_grid_and_tactile_frame) {
  const Config config = default_config().value();
  Engine engine(config);
  LT_CHECK(engine.latest_grid().status == GridStatus::kNoFrame);
  LT_CHECK(!engine.encode_legacy(engine.latest_grid(), UnknownCellPolicy::kFlat));  // 没数据不发帧

  // 启动序列的 IN 响应：两份标定按分片喂进去
  const auto blob0 = lt_files::read("cs30/calibration_0.bin");
  const auto blob1 = lt_files::read("cs30/calibration_1.bin");
  const auto s0 = slices(blob0), s1 = slices(blob1);
  size_t k0 = 0, k1 = 0;
  for (size_t i = 0; i < Engine::startup_step_count(); ++i) {
    const cs30::Step& s = Engine::startup_step(i);
    if (!s.is_in()) continue;
    if (s.value == 0xc100) {
      LT_CHECK(engine.on_startup_response(i, s0[k0].data(), s0[k0].size()));
      ++k0;
    }
    if (s.value == 0xc200) {
      LT_CHECK(engine.on_startup_response(i, s1[k1].data(), s1[k1].size()));
      ++k1;
    }
  }
  Status started = engine.finish_startup();
  LT_CHECK_MSG(started, started.message);
  LT_CHECK(engine.intrinsics() && engine.intrinsics()->width == 640);
  std::printf("  %s\n", engine.device_summary().c_str());

  // 合成一帧：地面 + 箱子
  const CameraIntrinsics in = *engine.intrinsics();
  DepthCameraModel model = DepthCameraModel::create(in, true).value();
  lt_synth::Scene scene;
  scene.boxes.push_back({-0.15, 0.15, 1.85, 2.15, 0.0, 0.5});
  const DepthFrame frame = lt_synth::render(scene, model, {1.5, 30, 0}, DepthMeaning::kOpticalAxisZ);

  push_frame(engine, frame, 0);
  OccupancyGrid g;
  LT_CHECK(wait_for_frame(engine, 1, &g));
  // 与直接调用流水线的结果完全一致
  DepthPipeline direct(config);
  LT_CHECK(direct.set_intrinsics(in));
  const OccupancyGrid expected = direct.process(frame);
  LT_CHECK(g.status == GridStatus::kOk && g.cells == expected.cells);
  LT_CHECK(g.cells[cell_index(3, 4)] == CellState::kOccupied);

  DepthFrame back;
  LT_CHECK(engine.latest_frame(&back) && back.depth_mm == frame.depth_mm);  // 拆帧逐字节还原

  // 触觉帧：状态 2 的表示方式必须显式给
  LT_CHECK(!engine.encode_legacy(g, static_cast<UnknownCellPolicy>(0)));
  Result<LegacyFrame> tactile = engine.encode_legacy(g, UnknownCellPolicy::kFlat);
  LT_CHECK(tactile);
  Result<LegacyFrame> reference = encode_legacy_frame(expected.cells, UnknownCellPolicy::kFlat, LegacyBoardLayout{true, true});
  LT_CHECK(tactile && reference && tactile.value() == reference.value());

  // 存帧 → 再核对这个帧文件：摘要与直接计算相同，帧文件与原始深度逐字节相同
  const std::string path = std::string(LINGTOUCH_TEST_TMP) + "/engine_saved_frame.bin";
  LT_CHECK(engine.save_latest_frame(path));
  const auto saved = lt_files::read_abs(path);
  LT_CHECK(saved.size() == cs30::kFrameBytes);
  Result<OccupancyGrid> again = engine.process_frame_file(path);
  LT_CHECK_MSG(again, again.error());
  if (again) LT_CHECK(grid_digest(again.value()) == grid_digest(expected));
  LT_CHECK(grid_json(g, monotonic_now_ns()).find("\"digest\":\"" + grid_digest(expected) + "\"") != std::string::npos);
  std::printf("  合成帧栅格摘要 %s\n", grid_digest(expected).c_str());

  // 第二帧（FID 翻转）
  push_frame(engine, frame, 1);
  LT_CHECK(wait_for_frame(engine, 2, &g));
  const EngineStats st = engine.stats();
  LT_CHECK(st.assembler.frames == 2 && st.assembler.incomplete == 0 && st.assembler.bad_header == 0);
  std::printf("  传输 %llu 个，拼出 %llu 帧，处理 %llu 帧，上一帧用时 %.1f ms\n",
              static_cast<unsigned long long>(st.transfers), static_cast<unsigned long long>(st.assembler.frames),
              static_cast<unsigned long long>(st.frames_processed), st.last_process_ms);
}

LT_TEST_MAIN()
