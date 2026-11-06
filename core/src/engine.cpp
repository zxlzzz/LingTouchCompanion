#include "lingtouch/engine.h"

#include <chrono>
#include <cstdio>
#include <fstream>
#include <iterator>
#include <utility>

#include "lingtouch/perception/cs30_calibration.h"
#include "lingtouch/perception/pipeline.h"

namespace lingtouch {
namespace {

int64_t now_ns() {
  return std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now().time_since_epoch())
      .count();
}

void size_frame(DepthFrame* f) {
  f->width = cs30::kWidth;
  f->height = cs30::kHeight;
  f->depth_mm.assign(static_cast<size_t>(cs30::kWidth) * cs30::kHeight, 0);
}

}  // namespace

Engine::Engine(const Config& config)
    : config_(config),
      pipeline_(std::make_unique<DepthPipeline>(config)),
      assembler_(cs30::kFrameBytes, [this](const uint8_t* data, size_t size) { on_frame(data, size); }) {
  size_frame(&pending_);
  worker_ = std::thread([this] { worker_loop(); });
}

Engine::~Engine() {
  {
    std::lock_guard<std::mutex> lock(pending_mutex_);
    stopping_ = true;
  }
  pending_cv_.notify_all();
  if (worker_.joinable()) worker_.join();
}

size_t Engine::startup_step_count() { return cs30::startup_step_count(); }

const cs30::Step& Engine::startup_step(size_t index) { return cs30::startup_steps()[index]; }

Status Engine::on_startup_response(size_t step_index, const uint8_t* data, size_t size) {
  std::lock_guard<std::mutex> lock(startup_mutex_);
  return collector_.on_response(step_index, data, size);
}

Status Engine::finish_startup() {
  cs30::DeviceInfo info;
  {
    std::lock_guard<std::mutex> lock(startup_mutex_);
    info = collector_.info();
  }
  std::string problems;
  for (int which = 0; which < 2; ++which) {
    if (!info.calibration_complete[which]) {
      problems += "标定 " + std::to_string(which) + " 没收全；";
      continue;
    }
    Result<cs30::Calibration> cal =
        cs30::decode_calibration(info.calibration[which].data(), info.calibration[which].size());
    if (!cal) {
      problems += "标定 " + std::to_string(which) + "：" + cal.error() + "；";
      continue;
    }
    if (cal.value().depth.width == cs30::kWidth && cal.value().depth.height == cs30::kHeight)
      return set_intrinsics(cal.value().depth);
    problems += "标定 " + std::to_string(which) + " 是 " + std::to_string(cal.value().depth.width) + "×" +
                std::to_string(cal.value().depth.height) + "；";
  }
  return Status::failure("没有可用的 640×480 深度内参：" + problems);
}

std::string Engine::device_summary() const {
  cs30::DeviceInfo info;
  {
    std::lock_guard<std::mutex> lock(startup_mutex_);
    info = collector_.info();
  }
  std::string s = "子型号 " + cs30::printable(info.subtype) + "；固件 " + cs30::printable(info.firmware) + "；序列号 " +
                  cs30::printable(info.serial) + "；标定 0 " + std::to_string(info.calibration[0].size()) + " 字节" +
                  (info.calibration_complete[0] ? "" : "（未收全）") + "；标定 1 " +
                  std::to_string(info.calibration[1].size()) + " 字节" +
                  (info.calibration_complete[1] ? "" : "（未收全）");
  std::optional<CameraIntrinsics> in = intrinsics();
  s += in ? "；内参 " + in->id : "；内参 未设定";
  return s;
}

Status Engine::set_intrinsics(const CameraIntrinsics& intrinsics) {
  std::lock_guard<std::mutex> lock(pipeline_mutex_);
  Status s = pipeline_->set_intrinsics(intrinsics);
  if (s) intrinsics_ = intrinsics;
  return s;
}

Status Engine::set_calibration_blob(const uint8_t* blob, size_t size) {
  Result<cs30::Calibration> cal = cs30::decode_calibration(blob, size);
  if (!cal) return Status::failure(cal.error());
  return set_intrinsics(cal.value().depth);
}

std::optional<CameraIntrinsics> Engine::intrinsics() const {
  std::lock_guard<std::mutex> lock(pipeline_mutex_);
  return intrinsics_;
}

void Engine::push_iso_transfer(const uint8_t* buffer, size_t size, const IsoPacketDesc* descs, size_t count) {
  std::lock_guard<std::mutex> lock(assembler_mutex_);
  assembler_.push_transfer(buffer, size, descs, count);
  std::lock_guard<std::mutex> result(result_mutex_);
  ++stats_.transfers;
  stats_.assembler = assembler_.stats();
}

void Engine::reset_stream() {
  std::lock_guard<std::mutex> lock(assembler_mutex_);
  assembler_.reset();
}

// 在 assembler_mutex_ 内被调用。加锁顺序：assembler → pending → result。
void Engine::on_frame(const uint8_t* data, size_t size) {
  std::lock_guard<std::mutex> lock(pending_mutex_);
  if (pending_ready_) {
    std::lock_guard<std::mutex> result(result_mutex_);
    ++stats_.frames_dropped_busy;
  }
  const size_t n = size / 2;
  uint16_t* out = pending_.depth_mm.data();
  for (size_t i = 0; i < n; ++i) out[i] = static_cast<uint16_t>(data[2 * i] | (data[2 * i + 1] << 8));  // 小端
  pending_.frame_id = next_frame_id_++;
  pending_.capture_time_ns = now_ns();
  pending_ready_ = true;
  pending_cv_.notify_one();
}

void Engine::worker_loop() {
  DepthFrame frame;
  size_frame(&frame);
  for (;;) {
    {
      std::unique_lock<std::mutex> lock(pending_mutex_);
      pending_cv_.wait(lock, [this] { return pending_ready_ || stopping_; });
      if (stopping_) return;
      std::swap(frame, pending_);
      pending_ready_ = false;
    }
    const auto t0 = std::chrono::steady_clock::now();
    OccupancyGrid grid;
    {
      std::lock_guard<std::mutex> lock(pipeline_mutex_);
      frame.intrinsics_id = intrinsics_ ? intrinsics_->id : std::string();
      grid = pipeline_->process(frame);
    }
    const double ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
    std::lock_guard<std::mutex> lock(result_mutex_);
    latest_grid_ = grid;
    latest_frame_ = frame;
    has_frame_ = true;
    ++stats_.frames_processed;
    stats_.last_process_ms = ms;
  }
}

OccupancyGrid Engine::latest_grid() const {
  std::lock_guard<std::mutex> lock(result_mutex_);
  return latest_grid_;
}

bool Engine::latest_frame(DepthFrame* out) const {
  std::lock_guard<std::mutex> lock(result_mutex_);
  if (!has_frame_) return false;
  *out = latest_frame_;
  return true;
}

EngineStats Engine::stats() const {
  std::lock_guard<std::mutex> lock(result_mutex_);
  return stats_;
}

Status Engine::save_latest_frame(const std::string& path) const {
  DepthFrame f;
  if (!latest_frame(&f)) return Status::failure("还没有收到帧");
  std::ofstream out(path, std::ios::binary);
  if (!out) return Status::failure("打不开文件：" + path);
  for (uint16_t v : f.depth_mm) {
    const char b[2] = {static_cast<char>(v & 0xff), static_cast<char>(v >> 8)};
    out.write(b, 2);
  }
  return out ? Status::success() : Status::failure("写文件失败：" + path);
}

Result<OccupancyGrid> Engine::process_frame_file(const std::string& path) {
  std::ifstream in(path, std::ios::binary);
  if (!in) return Result<OccupancyGrid>::failure("打不开文件：" + path);
  const std::vector<uint8_t> raw((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
  if (raw.size() != cs30::kFrameBytes)
    return Result<OccupancyGrid>::failure("帧文件应为 614400 字节，实际 " + std::to_string(raw.size()));
  DepthFrame f;
  size_frame(&f);
  for (size_t i = 0; i < f.depth_mm.size(); ++i) f.depth_mm[i] = static_cast<uint16_t>(raw[2 * i] | (raw[2 * i + 1] << 8));
  std::lock_guard<std::mutex> lock(pipeline_mutex_);
  if (!intrinsics_) return Result<OccupancyGrid>::failure("没有可用内参");
  // 用一条独立的流水线，不动后台线程正在用的那条
  DepthPipeline pipeline(config_);
  Status s = pipeline.set_intrinsics(*intrinsics_);
  if (!s) return Result<OccupancyGrid>::failure(s.message);
  f.intrinsics_id = intrinsics_->id;
  return Result<OccupancyGrid>::success(pipeline.process(f));
}

Result<LegacyFrame> Engine::encode_legacy(const OccupancyGrid& grid, UnknownCellPolicy policy) const {
  if (grid.status == GridStatus::kNoFrame || grid.status == GridStatus::kNoCalibration)
    return Result<LegacyFrame>::failure(std::string("没有可用的栅格（") + grid_status_name(grid.status) + "），不发帧");
  return encode_legacy_frame(grid.cells, policy,
                             LegacyBoardLayout{config_.tactile.mirror_left_right, config_.tactile.module_rot180});
}

}  // namespace lingtouch
