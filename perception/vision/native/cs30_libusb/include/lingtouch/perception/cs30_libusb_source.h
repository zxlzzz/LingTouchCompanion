// Android fd path: Java force-claims once; libusb records the same file-description claims.
#pragma once
#include <array>
#include <atomic>
#include <condition_variable>
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
  static Result<std::unique_ptr<Cs30LibusbSource>> open_fd(int fd, Engine*, LogFn);
  static Result<std::unique_ptr<Cs30LibusbSource>> open_vid_pid(uint16_t, uint16_t, Engine*, LogFn);
  static std::string interface_info(int fd, int interface_number);
  static bool supports_interface(int number) { return number >= 0 && number < 2; }
  ~Cs30LibusbSource();
  Cs30LibusbSource(const Cs30LibusbSource&) = delete;
  Cs30LibusbSource& operator=(const Cs30LibusbSource&) = delete;
  Status start(bool restore_stream_idle = false);
  // Failure preserves transfers, event pump, device handle and owned dup fd for a retry.
  Status stop();
  // After reset, close/reopen through Java and force-claim again before starting.
  Status reset_device();
  // Android may recover once from a stream alt or initial ISO submission failure.
  // A successful reset requires a fresh platform connection before another start.
  enum class Recovery { Unavailable = 0, Reopen = 1, Rediscover = 2 };
  Recovery reset_after_startup_error();
  bool streaming() const { return streaming_.load(); }
  uint64_t transfer_errors() const { return transfer_errors_.load(); }
  double last_transfer_age_ms() const;
  int last_transfer_status() const { return last_transfer_status_.load(); }
 private:
  Cs30LibusbSource(libusb_context*, libusb_device_handle*, Engine*, LogFn, bool wrapped, int owned_fd);
  static void on_transfer(libusb_transfer*);
  void handle_transfer(libusb_transfer*);
  Status claim(int);
  Status queue_iso(uint8_t,uint32_t,uint32_t,uint32_t,uint32_t);
  Status submit_iso_queue(uint8_t endpoint, uint32_t count, uint32_t packet_bytes,
                         uint32_t packets, uint32_t timeout, int& error_code);
  Status drain_iso_queue_locked();
  void free_iso_queue_locked();
  void start_events();
  void stop_events();
  Status stop_locked();
  Status release_all();
  void prepare_configuration();
  void log(const std::string&) const;
  libusb_context* ctx_;
  libusb_device_handle* handle_;
  Engine* engine_;
  LogFn log_;
  bool wrapped_;
  int owned_fd_;
  std::mutex lifecycle_mutex_;
  std::mutex transfers_mutex_;
  std::condition_variable drained_;
  std::vector<libusb_transfer*> transfers_;
  std::vector<std::vector<uint8_t>> buffers_;
  std::vector<bool> in_flight_;
  std::vector<IsoPacketDesc> descs_;
  std::array<bool,2> claimed_{{false,false}};
  enum class StartupFailure { None, IsoSubmitIo, StreamingAlt };
  StartupFailure startup_failure_ = StartupFailure::None; // Guarded by lifecycle_mutex_.
  bool control_alt_zero_only_ = false;
  std::atomic<bool> submitting_{false}, streaming_{false}, events_running_{false};
  int pending_ = 0; // Every reservation is made before submit; protected by transfers_mutex_.
  std::atomic<uint64_t> transfer_errors_{0};
  std::atomic<int64_t> last_transfer_ns_{0};
  std::atomic<int> last_transfer_status_{0};
  std::thread events_;
};
}
