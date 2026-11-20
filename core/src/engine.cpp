#include "lingtouch/engine.h"

#include <chrono>
#include <cmath>
#include <cstdio>
#include <fstream>
#include <iterator>
#include <utility>

#include "lingtouch/perception/cs30_calibration.h"
#include "lingtouch/perception/pipeline.h"
#include "monotonic_time.h"

namespace lingtouch {
namespace {

void size_frame(DepthFrame* f) {
  f->width = cs30::kWidth;
  f->height = cs30::kHeight;
  f->depth_mm.assign(static_cast<size_t>(cs30::kWidth) * cs30::kHeight, 0);
}

bool same_intrinsics(const CameraIntrinsics& a,const CameraIntrinsics& b) {
  return a.id==b.id && a.width==b.width && a.height==b.height &&
      a.fx==b.fx && a.fy==b.fy && a.cx==b.cx && a.cy==b.cy &&
      a.k1==b.k1 && a.k2==b.k2 && a.k3==b.k3 && a.p1==b.p1 && a.p2==b.p2;
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
  {
    std::lock_guard<std::mutex> startup(startup_mutex_);
    collector_.reset();
  }
  std::lock_guard<std::mutex> pending(pending_mutex_);
  ++capture_session_;
  pending_ready_ = false;
  pending_intrinsics_.reset();
  std::lock_guard<std::mutex> result(result_mutex_);
  latest_frame_ = DepthFrame{};
  latest_grid_ = OccupancyGrid{};
  has_frame_ = false;
}

Status Engine::submit_frame(const FrameBundle& bundle) {
  const DepthFrame& frame = bundle.depth;
  if (!bundle.calibration) return Status::failure("采集帧缺少标定");
  const auto& in = bundle.calibration->depth;
  const double params[]={in.fx,in.fy,in.cx,in.cy,in.k1,in.k2,in.k3,in.p1,in.p2};
  for(double p:params)if(!std::isfinite(p))return Status::failure("采集帧标定包含非有限数值");
  if(in.fx<=0 || in.fy<=0 || in.cx<0 || in.cy<0 || in.cx>=in.width || in.cy>=in.height)
    return Status::failure("采集帧标定参数无效");
  if (frame.width <= 0 || frame.height <= 0 || frame.width != in.width || frame.height != in.height ||
      frame.depth_mm.size() != static_cast<size_t>(frame.width) * static_cast<size_t>(frame.height))
    return Status::failure("采集帧尺寸与标定不一致");
  std::lock_guard<std::mutex> pending(pending_mutex_);
  if (stopping_) return Status::failure("核心正在关闭");
  if (pending_ready_) {
    std::lock_guard<std::mutex> result(result_mutex_);
    ++stats_.frames_dropped_busy;
  }
  pending_ = frame;
  pending_intrinsics_ = in;
  pending_session_ = capture_session_;
  pending_ready_ = true;
  pending_cv_.notify_one();
  return Status::success();
}

// 在 assembler_mutex_ 内被调用。加锁顺序：assembler → pending → result。
void Engine::on_frame(const uint8_t* data, size_t size) {
  std::lock_guard<std::mutex> lock(pending_mutex_);
  if (pending_ready_) {
    std::lock_guard<std::mutex> result(result_mutex_);
    ++stats_.frames_dropped_busy;
  }
  const size_t n = size / 2;
  if (size != cs30::kFrameBytes) return;
  if (pending_.width != cs30::kWidth || pending_.height != cs30::kHeight || pending_.depth_mm.size()!=n)
    size_frame(&pending_);
  uint16_t* out = pending_.depth_mm.data();
  for (size_t i = 0; i < n; ++i) out[i] = static_cast<uint16_t>(data[2 * i] | (data[2 * i + 1] << 8));  // 小端
  pending_.frame_id = next_frame_id_++;
  pending_.capture_time_ns = monotonic_time_ns();
  pending_intrinsics_.reset();
  pending_session_ = capture_session_;
  pending_ready_ = true;
  pending_cv_.notify_one();
}

void Engine::worker_loop() {
  DepthFrame frame;
  size_frame(&frame);
  for (;;) {
    uint64_t session = 0;
    std::optional<CameraIntrinsics> captured_intrinsics;
    {
      std::unique_lock<std::mutex> lock(pending_mutex_);
      pending_cv_.wait(lock, [this] { return pending_ready_ || stopping_; });
      if (stopping_) return;
      std::swap(frame, pending_);
      session = pending_session_;
      captured_intrinsics = pending_intrinsics_;
      pending_ready_ = false;
    }
    const auto t0 = std::chrono::steady_clock::now();
    OccupancyGrid grid;
    {
      std::lock_guard<std::mutex> lock(pipeline_mutex_);
      {
        std::lock_guard<std::mutex> pending(pending_mutex_);
        // A discarded frame must not restore its calibration after a new
        // session (or a caller's explicit calibration update) has begun.
        if(session!=capture_session_)continue;
      }
      if (captured_intrinsics && (!intrinsics_ || !same_intrinsics(*intrinsics_,*captured_intrinsics))) {
        const Status configured = pipeline_->set_intrinsics(*captured_intrinsics);
        if (!configured) continue;
        intrinsics_ = captured_intrinsics;
      }
      frame.intrinsics_id = intrinsics_ ? intrinsics_->id : std::string();
      grid = pipeline_->process(frame);
    }
    const double ms = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - t0).count();
    std::lock_guard<std::mutex> pending(pending_mutex_);
    if (session != capture_session_) continue;
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
