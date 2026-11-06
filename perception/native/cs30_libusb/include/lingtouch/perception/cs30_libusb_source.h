// 用上游 libusb 收 CS30 等时流（安卓；桌面 Linux 也能编）。
//
// 安卓：Kotlin 里 UsbManager 授权、openDevice 后把 getFileDescriptor() 交给 open_fd；
// 本类按 Engine::startup_step() 那张表（来自 startup_sequence.json）逐步执行，
// 挂等时传输，收到的传输按批交给 Engine::push_iso_transfer。
// 内核若已用 uvcvideo 绑定接口，claim 时自动 detach（release 时再交还）。
#pragma once

#include <atomic>
#include <cstdint>
#include <functional>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include "lingtouch/engine.h"
#include "lingtouch/result.h"

struct libusb_context;
struct libusb_device_handle;
struct libusb_transfer;

namespace lingtouch {

class Cs30LibusbSource {
 public:
  using LogFn = std::function<void(const std::string&)>;

  // fd 由调用方持有：本类不关闭它（libusb_close 也不会关）；调用方在本对象销毁后再关闭连接。
  static Result<std::unique_ptr<Cs30LibusbSource>> open_fd(int fd, Engine* engine, LogFn log);
  // 桌面 Linux 主机上按 VID/PID 打开（需要对 /dev/bus/usb 有权限）。
  static Result<std::unique_ptr<Cs30LibusbSource>> open_vid_pid(uint16_t vid, uint16_t pid, Engine* engine, LogFn log);

  ~Cs30LibusbSource();
  Cs30LibusbSource(const Cs30LibusbSource&) = delete;
  Cs30LibusbSource& operator=(const Cs30LibusbSource&) = delete;

  // 走完启动序列并开始收流。失败时已经清理（release），可以再调一次重开。
  Status start();
  // 停流：取消并排空所有传输 → 接口 1 设 alt 0 → 接口 0 设 alt 0 → release。
  void stop();
  // release 后重开仍不行时再用（REPORT「安全和恢复」）。
  Status reset_device();

  bool streaming() const { return streaming_.load(); }
  uint64_t transfer_errors() const { return transfer_errors_.load(); }

 private:
  Cs30LibusbSource(libusb_context* ctx, libusb_device_handle* handle, Engine* engine, LogFn log);
  static void on_transfer(libusb_transfer* transfer);
  void handle_transfer(libusb_transfer* transfer);
  void prepare_configuration();
  Status claim(int interface_number);
  Status queue_iso(uint8_t endpoint, uint32_t count, uint32_t bytes, uint32_t packets, uint32_t timeout_ms);
  void start_events();
  void stop_events();
  void release_all();
  void log(const std::string& message) const;

  libusb_context* ctx_;
  libusb_device_handle* handle_;
  Engine* engine_;
  LogFn log_;

  std::vector<libusb_transfer*> transfers_;
  std::vector<std::vector<uint8_t>> buffers_;
  std::vector<IsoPacketDesc> descs_;  // 只在事件线程里用
  bool claimed_[2] = {false, false};

  std::atomic<bool> submitting_{false};
  std::atomic<bool> streaming_{false};
  std::atomic<int> pending_{0};
  std::atomic<bool> events_running_{false};
  std::atomic<uint64_t> transfer_errors_{0};
  std::thread events_;
};

}  // namespace lingtouch
