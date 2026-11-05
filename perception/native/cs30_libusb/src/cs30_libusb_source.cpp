#include "lingtouch/perception/cs30_libusb_source.h"

#include <libusb.h>

#include <chrono>
#include <cstdio>

#include "lingtouch/perception/cs30_protocol.h"

namespace lingtouch {
namespace {

std::string usb_error(const char* what, int code) {
  return std::string(what) + "：" + libusb_error_name(code) + "（" + std::to_string(code) + "）";
}

// libusb 自己的告警（如 submiturb failed, errno=…）比错误名更细，转进同一份日志，手机上不用 adb 也能看到
Cs30LibusbSource::LogFn g_libusb_log;

void on_libusb_log(libusb_context*, enum libusb_log_level, const char* message) {
  if (!g_libusb_log) return;
  std::string line(message);
  while (!line.empty() && (line.back() == '\n' || line.back() == '\r')) line.pop_back();
  g_libusb_log("libusb：" + line);
}

std::string step_name(size_t i, const cs30::Step& s) {
  char buf[96];
  if (s.kind == cs30::StepKind::kControl)
    std::snprintf(buf, sizeof(buf), "第 %zu 步 %s 0x%04x", i, s.is_in() ? "GET" : "SET", s.value);
  else
    std::snprintf(buf, sizeof(buf), "第 %zu 步", i);
  return buf;
}

}  // namespace

Cs30LibusbSource::Cs30LibusbSource(libusb_context* ctx, libusb_device_handle* handle, Engine* engine, LogFn log)
    : ctx_(ctx), handle_(handle), engine_(engine), log_(std::move(log)) {}

Result<std::unique_ptr<Cs30LibusbSource>> Cs30LibusbSource::open_fd(int fd, Engine* engine, LogFn log) {
  using R = Result<std::unique_ptr<Cs30LibusbSource>>;
  libusb_context* ctx = nullptr;
  // 安卓非 root：跳过设备枚举，直接包住 UsbManager 给的 fd（上游 android/README）
  g_libusb_log = log;
  libusb_init_option options[3];
  options[0].option = LIBUSB_OPTION_NO_DEVICE_DISCOVERY;
  options[0].value.ival = 0;
  options[1].option = LIBUSB_OPTION_LOG_LEVEL;
  options[1].value.ival = LIBUSB_LOG_LEVEL_WARNING;
  options[2].option = LIBUSB_OPTION_LOG_CB;
  options[2].value.log_cbval = on_libusb_log;
  int r = libusb_init_context(&ctx, options, 3);
  if (r != 0) return R::failure(usb_error("libusb_init_context", r));
  libusb_device_handle* handle = nullptr;
  r = libusb_wrap_sys_device(ctx, static_cast<intptr_t>(fd), &handle);
  if (r != 0) {
    libusb_exit(ctx);
    return R::failure(usb_error("libusb_wrap_sys_device", r));
  }
  return R::success(std::unique_ptr<Cs30LibusbSource>(new Cs30LibusbSource(ctx, handle, engine, std::move(log))));
}

Result<std::unique_ptr<Cs30LibusbSource>> Cs30LibusbSource::open_vid_pid(uint16_t vid, uint16_t pid, Engine* engine,
                                                                       LogFn log) {
  using R = Result<std::unique_ptr<Cs30LibusbSource>>;
  libusb_context* ctx = nullptr;
  int r = libusb_init_context(&ctx, nullptr, 0);
  if (r != 0) return R::failure(usb_error("libusb_init_context", r));
  libusb_device_handle* handle = libusb_open_device_with_vid_pid(ctx, vid, pid);
  if (handle == nullptr) {
    libusb_exit(ctx);
    return R::failure("找不到或打不开 CS30（2207:0016）");
  }
  return R::success(std::unique_ptr<Cs30LibusbSource>(new Cs30LibusbSource(ctx, handle, engine, std::move(log))));
}

Cs30LibusbSource::~Cs30LibusbSource() {
  stop();
  libusb_close(handle_);  // 包装的 fd 不会被关闭
  libusb_exit(ctx_);
}

void Cs30LibusbSource::log(const std::string& message) const {
  if (log_) log_(message);
}

void Cs30LibusbSource::prepare_configuration() {
  log("USB 速度代码 " + std::to_string(libusb_get_device_speed(libusb_get_device(handle_))) + "（3 = 高速，2 = 全速）");
  int active = -1;
  int r = libusb_get_configuration(handle_, &active);
  if (r != 0) {
    log(usb_error("读当前配置", r));
    return;
  }
  log("当前 USB 配置 " + std::to_string(active));
  if (active != 0) return;
  // 手机认为供电不够时内核会不选配置，这时接口不可用；相机实际由外部供电，手动选上
  r = libusb_set_configuration(handle_, 1);
  log(r == 0 ? std::string("相机未配置，已手动选配置 1") : usb_error("选配置 1", r));
}

Status Cs30LibusbSource::claim(int interface_number) {
  if (claimed_[interface_number]) return Status::success();
  // 内核若已用 uvcvideo 绑定，claim 时自动 detach，release 时交还；不需要 root
  libusb_set_auto_detach_kernel_driver(handle_, 1);
  const int r = libusb_claim_interface(handle_, interface_number);
  if (r != 0) return Status::failure(usb_error(("claim 接口 " + std::to_string(interface_number)).c_str(), r));
  claimed_[interface_number] = true;
  return Status::success();
}

void Cs30LibusbSource::start_events() {
  if (events_running_.exchange(true)) return;
  events_ = std::thread([this] {
    while (events_running_.load()) {
      timeval tv{0, 100000};
      libusb_handle_events_timeout_completed(ctx_, &tv, nullptr);
    }
  });
}

void Cs30LibusbSource::stop_events() {
  if (!events_running_.exchange(false)) return;
  libusb_interrupt_event_handler(ctx_);
  if (events_.joinable()) events_.join();
}

Status Cs30LibusbSource::queue_iso(uint8_t endpoint, uint32_t count, uint32_t bytes, uint32_t packets,
                                   uint32_t timeout_ms) {
  if (packets == 0 || bytes % packets != 0) return Status::failure("等时传输参数不合法");
  submitting_ = true;
  transfers_.assign(count, nullptr);
  buffers_.assign(count, std::vector<uint8_t>(bytes));
  for (uint32_t k = 0; k < count; ++k) {
    libusb_transfer* t = libusb_alloc_transfer(static_cast<int>(packets));
    if (t == nullptr) return Status::failure("libusb_alloc_transfer 失败");
    transfers_[k] = t;
    libusb_fill_iso_transfer(t, handle_, endpoint, buffers_[k].data(), static_cast<int>(bytes),
                             static_cast<int>(packets), &Cs30LibusbSource::on_transfer, this, timeout_ms);
    libusb_set_iso_packet_lengths(t, bytes / packets);
    const int r = libusb_submit_transfer(t);
    if (r != 0) return Status::failure(usb_error("libusb_submit_transfer", r));
    ++pending_;
  }
  log("已挂 " + std::to_string(count) + " 个等时传输（每个 " + std::to_string(packets) + " 个微帧）");
  return Status::success();
}

void Cs30LibusbSource::on_transfer(libusb_transfer* transfer) {
  static_cast<Cs30LibusbSource*>(transfer->user_data)->handle_transfer(transfer);
}

void Cs30LibusbSource::handle_transfer(libusb_transfer* t) {
  if (t->status == LIBUSB_TRANSFER_COMPLETED) {
    descs_.resize(static_cast<size_t>(t->num_iso_packets));
    for (int k = 0; k < t->num_iso_packets; ++k) {
      const libusb_iso_packet_descriptor& d = t->iso_packet_desc[k];
      descs_[k] = IsoPacketDesc{d.length, d.actual_length, static_cast<int32_t>(d.status)};
    }
    engine_->push_iso_transfer(t->buffer, static_cast<size_t>(t->length), descs_.data(), descs_.size());
  } else if (t->status != LIBUSB_TRANSFER_CANCELLED) {
    ++transfer_errors_;
  }
  if (submitting_.load() && t->status != LIBUSB_TRANSFER_NO_DEVICE && t->status != LIBUSB_TRANSFER_CANCELLED) {
    if (libusb_submit_transfer(t) == 0) return;  // 仍在途中
    ++transfer_errors_;
  }
  if (t->status == LIBUSB_TRANSFER_NO_DEVICE) {
    submitting_ = false;
    streaming_ = false;
  }
  --pending_;
}

Status Cs30LibusbSource::start() {
  if (streaming_.load()) return Status::success();
  if (pending_.load() > 0)
    return Status::failure("上次停流时还有传输没回来，缓冲不能复用；请拔插相机后重新打开");
  engine_->reset_stream();
  prepare_configuration();
  Status s = claim(cs30::kControlInterface);  // REPORT 第 1 步：claim 接口 0
  for (size_t i = 0; s && i < Engine::startup_step_count(); ++i) {
    const cs30::Step& st = Engine::startup_step(i);
    switch (st.kind) {
      case cs30::StepKind::kControl: {
        // 每条等上一条完成再发，不加 sleep；Commit 正常约 2.36 s，超时给 15 s
        std::vector<uint8_t> in(st.is_in() ? st.length : 0);
        uint8_t* data = st.is_in() ? in.data() : const_cast<uint8_t*>(st.data);
        const int r = libusb_control_transfer(handle_, st.request_type, st.request, st.value, st.index, data,
                                              st.length, cs30::kControlTimeoutMs);
        if (r < 0) {
          s = Status::failure(usb_error(step_name(i, st).c_str(), r));
        } else if (st.is_in()) {
          s = engine_->on_startup_response(i, in.data(), static_cast<size_t>(r));
        } else if (r != st.data_length) {
          s = Status::failure(step_name(i, st) + "：只发出 " + std::to_string(r) + " 字节");
        }
        break;
      }
      case cs30::StepKind::kSetAlt: {
        s = claim(st.interface_number);
        if (!s) break;
        const int r = libusb_set_interface_alt_setting(handle_, st.interface_number, st.alt_setting);
        if (r != 0) s = Status::failure(usb_error(step_name(i, st).c_str(), r));
        break;
      }
      case cs30::StepKind::kQueueIso:
        start_events();  // 切到 alt 1 之后立刻挂传输，之后的控制请求在传输挂上之后再发
        s = queue_iso(cs30::kIsoEndpoint, st.iso_transfers, st.iso_transfer_bytes, st.iso_packets, st.iso_timeout_ms);
        break;
    }
    if (s && st.settle_ms > 0)
      std::this_thread::sleep_for(std::chrono::milliseconds(st.settle_ms));  // 事件线程照常处理传输
  }
  if (!s) {
    log("启动失败：" + s.message);
    stop();
    return s;
  }
  streaming_ = true;
  Status cal = engine_->finish_startup();
  log(cal ? "已开流，" + engine_->device_summary() : "已开流，但内参不可用：" + cal.message);
  return Status::success();
}

void Cs30LibusbSource::release_all() {
  for (int i = 1; i >= 0; --i) {
    if (!claimed_[i]) continue;
    libusb_release_interface(handle_, i);
    claimed_[i] = false;
  }
}

void Cs30LibusbSource::stop() {
  submitting_ = false;
  streaming_ = false;
  // 排空：最多等 3 s，期间事件线程继续处理回调。每轮都重新取消一次：
  // 回调可能恰好在 submitting_ 置 false 之前重新提交了传输。
  const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(3);
  while (pending_.load() > 0 && std::chrono::steady_clock::now() < deadline) {
    for (libusb_transfer* t : transfers_)
      if (t != nullptr) libusb_cancel_transfer(t);
    std::this_thread::sleep_for(std::chrono::milliseconds(10));
  }
  const int still_pending = pending_.load();
  stop_events();
  if (claimed_[cs30::kStreamingInterface]) libusb_set_interface_alt_setting(handle_, cs30::kStreamingInterface, 0);
  if (claimed_[cs30::kControlInterface]) libusb_set_interface_alt_setting(handle_, cs30::kControlInterface, 0);
  release_all();
  if (still_pending > 0) {
    // 仍在途中的传输不能释放，宁可泄漏也不释放正在使用的内存
    log("停流时还有 " + std::to_string(still_pending) + " 个传输没回来，未释放");
  } else {
    for (libusb_transfer* t : transfers_)
      if (t != nullptr) libusb_free_transfer(t);
    transfers_.clear();
    buffers_.clear();
  }
}

Status Cs30LibusbSource::reset_device() {
  stop();
  const int r = libusb_reset_device(handle_);
  if (r != 0) return Status::failure(usb_error("libusb_reset_device", r));
  return Status::success();
}

}  // namespace lingtouch
