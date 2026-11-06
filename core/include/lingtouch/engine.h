// 给 App 外壳调用的门面：安卓经 JNI、鸿蒙经 Node-API 都只调这一层。
//
// 数据流：外壳（或 cs30_libusb）按启动表执行控制请求，把 IN 响应交给 on_startup_response；
// 收到等时传输后按批调用 push_iso_transfer → 拆帧 → 后台线程算 9×6 栅格 → latest_grid()。
// 后台线程只保留最新一帧：上一帧还没算完时新帧替换旧帧（计入 frames_dropped_busy）。
#pragma once

#include <condition_variable>
#include <cstdint>
#include <memory>
#include <mutex>
#include <optional>
#include <string>
#include <thread>
#include <vector>

#include "lingtouch/config.h"
#include "lingtouch/perception/cs30_protocol.h"
#include "lingtouch/perception/uvc_frame_assembler.h"
#include "lingtouch/result.h"
#include "lingtouch/tactile.h"
#include "lingtouch/types.h"

namespace lingtouch {

class DepthPipeline;

struct EngineStats {
  AssemblerStats assembler;
  uint64_t transfers = 0;
  uint64_t frames_processed = 0;
  uint64_t frames_dropped_busy = 0;
  double last_process_ms = 0;
};

class Engine {
 public:
  explicit Engine(const Config& config);
  ~Engine();
  Engine(const Engine&) = delete;
  Engine& operator=(const Engine&) = delete;

  const Config& config() const { return config_; }

  // ---- CS30 启动序列（表来自 perception/cs30/startup_sequence.json）
  static size_t startup_step_count();
  static const cs30::Step& startup_step(size_t index);
  Status on_startup_response(size_t step_index, const uint8_t* data, size_t size);
  // 启动序列跑完后调用：从收到的标定 blob 解出 640×480 深度内参
  Status finish_startup();
  std::string device_summary() const;

  // ---- 内参（主机测试、以后换真标定都走这里）
  Status set_intrinsics(const CameraIntrinsics& intrinsics);
  Status set_calibration_blob(const uint8_t* blob, size_t size);
  std::optional<CameraIntrinsics> intrinsics() const;

  // ---- 收包：一个等时传输里的全部微帧一次传入
  void push_iso_transfer(const uint8_t* buffer, size_t size, const IsoPacketDesc* descs, size_t count);
  // 重新开流前调用：清掉拆了一半的帧
  void reset_stream();

  // ---- 结果
  OccupancyGrid latest_grid() const;
  bool latest_frame(DepthFrame* out) const;
  EngineStats stats() const;

  // ---- 真机验收用：把最近一帧原始深度存成文件（640×480 uint16 小端，与 perception/cs30/reference_*.bin 同格式）；
  //      对一个帧文件同步算栅格（不影响 latest_grid），用于两个平台、电脑之间比对摘要
  Status save_latest_frame(const std::string& path) const;
  Result<OccupancyGrid> process_frame_file(const std::string& path);

  // ---- 触觉：状态 2 的表示方式必须显式传入；镜像与 ROT180 取自配置
  Result<LegacyFrame> encode_legacy(const OccupancyGrid& grid, UnknownCellPolicy policy) const;

 private:
  void on_frame(const uint8_t* data, size_t size);
  void worker_loop();

  const Config config_;

  mutable std::mutex startup_mutex_;
  cs30::StartupCollector collector_;

  mutable std::mutex pipeline_mutex_;
  std::unique_ptr<DepthPipeline> pipeline_;
  std::optional<CameraIntrinsics> intrinsics_;

  std::mutex assembler_mutex_;
  UvcFrameAssembler assembler_;
  uint64_t next_frame_id_ = 1;

  std::mutex pending_mutex_;
  std::condition_variable pending_cv_;
  bool pending_ready_ = false;
  bool stopping_ = false;
  DepthFrame pending_;

  mutable std::mutex result_mutex_;
  OccupancyGrid latest_grid_;
  DepthFrame latest_frame_;
  bool has_frame_ = false;
  EngineStats stats_;

  std::thread worker_;
};

}  // namespace lingtouch
