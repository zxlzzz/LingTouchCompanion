#include "lingtouch/perception/cs30_libusb_source.h"
#include "lingtouch/perception/cs30_protocol.h"
#include <libusb.h>
#include <algorithm>
#include <cerrno>
#include <chrono>
#include <climits>
#include <cstring>
#include <map>
#if defined(__linux__) && !defined(CS30_SIMULATION)
#include <unistd.h>
#include <fcntl.h>
#include <sys/ioctl.h>
#include <linux/usbdevice_fs.h>
#endif
namespace lingtouch {
namespace {
std::mutex callbacks_mutex;
std::map<libusb_context*, Cs30LibusbSource::LogFn> callbacks;
void LIBUSB_CALL on_libusb_log(libusb_context* context, libusb_log_level, const char* message) {
  Cs30LibusbSource::LogFn callback;
  { std::lock_guard<std::mutex> lock(callbacks_mutex);auto it=callbacks.find(context);if(it!=callbacks.end())callback=it->second; }
  if(callback && message){std::string text(message);while(!text.empty()&&(text.back()=='\n'||text.back()=='\r'))text.pop_back();callback("libusb: "+text);}
}
void register_log(libusb_context* context,const Cs30LibusbSource::LogFn& callback){std::lock_guard<std::mutex> lock(callbacks_mutex);callbacks[context]=callback;}
void unregister_log(libusb_context* context){std::lock_guard<std::mutex> lock(callbacks_mutex);callbacks.erase(context);}
int64_t steady_ns(){return std::chrono::duration_cast<std::chrono::nanoseconds>(std::chrono::steady_clock::now().time_since_epoch()).count();}
std::string usb_error(const std::string& stage,int r) {
  return stage+": "+libusb_error_name(r)+" ("+std::to_string(r)+")";
}
void close_owned_fd(int fd) {
#if defined(__linux__) && !defined(CS30_SIMULATION)
  if(fd>=0)::close(fd);
#else
  (void)fd;
#endif
}
}
Cs30LibusbSource::Cs30LibusbSource(libusb_context* c,libusb_device_handle* h,Engine* e,LogFn fn,bool wrapped,int fd)
    :ctx_(c),handle_(h),engine_(e),log_(std::move(fn)),wrapped_(wrapped),owned_fd_(fd) {}
Result<std::unique_ptr<Cs30LibusbSource>> Cs30LibusbSource::open_fd(int fd,Engine* e,LogFn fn) {
  using R=Result<std::unique_ptr<Cs30LibusbSource>>;
  if(fd<0)return R::failure("Invalid USB fd");
  int wrapped_fd=fd,owned=-1;
#if defined(__linux__) && !defined(CS30_SIMULATION)
  // dup shares the kernel open-file description and its Java claims. It protects a late
  // callback from Java closing/reusing the original fd during deferred cleanup.
  owned=fcntl(fd,F_DUPFD_CLOEXEC,0);
  if(owned<0)return R::failure("dup USB fd failed: errno="+std::to_string(errno));
  wrapped_fd=owned;
#endif
  libusb_context* ctx=nullptr;
  libusb_init_option options[3]{};
  options[0].option=LIBUSB_OPTION_NO_DEVICE_DISCOVERY;
  options[1].option=LIBUSB_OPTION_LOG_LEVEL;options[1].value.ival=LIBUSB_LOG_LEVEL_WARNING;
  options[2].option=LIBUSB_OPTION_LOG_CB;options[2].value.log_cbval=on_libusb_log;
  int r=libusb_init_context(&ctx,options,3);
  if(r){close_owned_fd(owned);return R::failure(usb_error("libusb_init_context",r));}
  register_log(ctx,fn);
  libusb_device_handle* handle=nullptr;
  r=libusb_wrap_sys_device(ctx,static_cast<intptr_t>(wrapped_fd),&handle);
  if(r){libusb_exit(ctx);unregister_log(ctx);close_owned_fd(owned);return R::failure(usb_error("libusb_wrap_sys_device",r));}
  return R::success(std::unique_ptr<Cs30LibusbSource>(new Cs30LibusbSource(ctx,handle,e,std::move(fn),true,owned)));
}
Result<std::unique_ptr<Cs30LibusbSource>> Cs30LibusbSource::open_vid_pid(uint16_t vid,uint16_t pid,Engine* e,LogFn fn) {
  using R=Result<std::unique_ptr<Cs30LibusbSource>>;
  libusb_context* ctx=nullptr;
  libusb_init_option options[2]{};options[0].option=LIBUSB_OPTION_LOG_LEVEL;options[0].value.ival=LIBUSB_LOG_LEVEL_WARNING;
  options[1].option=LIBUSB_OPTION_LOG_CB;options[1].value.log_cbval=on_libusb_log;
  int r=libusb_init_context(&ctx,options,2);
  if(r)return R::failure(usb_error("libusb_init_context",r));
  register_log(ctx,fn);
  auto* h=libusb_open_device_with_vid_pid(ctx,vid,pid);
  if(!h){libusb_exit(ctx);unregister_log(ctx);return R::failure("Cannot open CS30");}
  return R::success(std::unique_ptr<Cs30LibusbSource>(new Cs30LibusbSource(ctx,h,e,std::move(fn),false,-1)));
}
Cs30LibusbSource::~Cs30LibusbSource() {
  // Normal owners call stop() and defer destruction on failure. This fallback also
  // refuses to destroy a callback's storage or context while a transfer is alive.
  while(!stop())std::this_thread::sleep_for(std::chrono::milliseconds(100));
  libusb_close(handle_);libusb_exit(ctx_);unregister_log(ctx_);close_owned_fd(owned_fd_);
}
void Cs30LibusbSource::log(const std::string& text) const {if(log_)log_(text);}
double Cs30LibusbSource::last_transfer_age_ms() const {const auto time=last_transfer_ns_.load();return time?static_cast<double>(steady_ns()-time)/1e6:-1.0;}
std::string Cs30LibusbSource::interface_info(int fd,int number) {
  std::string result="interface="+std::to_string(number)+", fd="+std::to_string(fd);
  if(number<0||number>255)return result+", invalid-interface";
#if defined(__linux__) && !defined(CS30_SIMULATION)
  usbdevfs_getdriver driver{};driver.interface=static_cast<unsigned int>(number);
  if(ioctl(fd,USBDEVFS_GETDRIVER,&driver)==0)result+=", driver="+std::string(driver.driver,strnlen(driver.driver,sizeof(driver.driver)));
  else result+=", GETDRIVER errno="+std::to_string(errno)+" ("+std::strerror(errno)+")";
#else
#ifdef CS30_SIMULATION
  result+=", driver=usbfs(simulated)";
#else
  result+=", driver query unavailable on this platform";
#endif
#endif
  return result;
}
Status Cs30LibusbSource::claim(int number) {
  if(!supports_interface(number))return Status::failure("Interface outside supported CS30 range: "+std::to_string(number));
  if(claimed_[number])return Status::success();
#ifdef _WIN32
  const int policy=0; // Windows libusbK/WinUSB does not implement kernel auto-detach.
#else
  const int policy=wrapped_?0:1;
#endif
  const int setting=libusb_set_auto_detach_kernel_driver(handle_,policy);
  log("claim policy interface="+std::to_string(number)+", auto_detach="+std::to_string(policy)+", result="+std::to_string(setting));
  if(setting!=0&&!(policy==0&&setting==LIBUSB_ERROR_NOT_SUPPORTED))return Status::failure(usb_error("set_auto_detach",setting));
  const int active=libusb_kernel_driver_active(handle_,number);
  const auto info=interface_info(owned_fd_,number)+", kernel_driver_active="+std::to_string(active);
  log("before native claim: "+info);
  const int r=libusb_claim_interface(handle_,number);
  if(r)return Status::failure(usb_error("claim interface "+std::to_string(number),r)+"; auto_detach="+std::to_string(policy)+"; "+info);
  claimed_[number]=true;log("native claim OK: "+std::to_string(number));return Status::success();
}
void Cs30LibusbSource::prepare_configuration() {
  log("USB speed="+std::to_string(libusb_get_device_speed(libusb_get_device(handle_)))+" (3=High Speed)");
  int configuration=-1;const int r=libusb_get_configuration(handle_,&configuration);
  if(r)log(usb_error("query USB configuration",r));
  else {
    log("USB configuration="+std::to_string(configuration));
    if(configuration==0)log("Device is unconfigured; check external PD power and reconnect. Configuration is not forced after Java claims.");
  }
  control_alt_zero_only_ = false;
  libusb_config_descriptor* descriptor = nullptr;
  const int described = libusb_get_active_config_descriptor(libusb_get_device(handle_), &descriptor);
  if (described != 0) {
    log(usb_error("read active configuration descriptor", described));
    return;
  }
  for (int i = 0; i < descriptor->bNumInterfaces; ++i) {
    const auto& entry = descriptor->interface[i];
    if (entry.num_altsetting == 1 && entry.altsetting[0].bInterfaceNumber == cs30::kControlInterface &&
        entry.altsetting[0].bAlternateSetting == 0) {
      control_alt_zero_only_ = true;
      break;
    }
  }
  libusb_free_config_descriptor(descriptor);
}
void Cs30LibusbSource::start_events() {
  if(events_running_.exchange(true))return;
  events_=std::thread([this]{while(events_running_.load()){
    timeval timeout{0,100000};const int r=libusb_handle_events_timeout_completed(ctx_,&timeout,nullptr);
    if(r!=0&&r!=LIBUSB_ERROR_INTERRUPTED){++transfer_errors_;std::this_thread::sleep_for(std::chrono::milliseconds(2));}
  }});
}
void Cs30LibusbSource::stop_events() {
  if(!events_running_.exchange(false))return;
  libusb_interrupt_event_handler(ctx_);if(events_.joinable())events_.join();
}
Status Cs30LibusbSource::queue_iso(uint8_t endpoint,uint32_t count,uint32_t bytes,uint32_t packets,uint32_t timeout) {
  if (!count || !packets || !bytes || count > 64 || packets > 1024 || bytes > INT_MAX ||
      bytes % packets) return Status::failure("Invalid isochronous transfer sizes");
  const uint32_t packet_bytes = bytes / packets;
  // Android usbfs can reject the 96 KiB requests used by the desktop SDK.
  // Keep the endpoint packet length, which is determined by the device.
  if (wrapped_) packets = std::min<uint32_t>(packets, 8);
  for (;;) {
    int error_code = 0;
    const auto status = submit_iso_queue(endpoint, count, packet_bytes, packets, timeout, error_code);
    if (status || !wrapped_ || error_code != LIBUSB_ERROR_NO_MEM || packets <= 2) return status;

    const uint32_t smaller = std::max<uint32_t>(packets / 2, 2);
    log("USB ISO allocation failed with " + std::to_string(packets) +
        " packets/transfer; draining queue and retrying with " + std::to_string(smaller) +
        " in the same USB session");
    // A later slot can fail after earlier slots were accepted. Keep the
    // interface, calibration collector and alt setting while retiring that queue.
    start_events();
    const auto drained = drain_iso_queue_locked();
    if (!drained) return Status::failure(status.message + "; " + drained.message);
    free_iso_queue_locked();
    packets = smaller;
  }
}
Status Cs30LibusbSource::submit_iso_queue(uint8_t endpoint, uint32_t count, uint32_t packet_bytes,
                                         uint32_t packets, uint32_t timeout, int& error_code) {
  const uint32_t bytes = packet_bytes * packets;
  // Allocate stable storage before the event pump can enter a callback.
  transfers_.assign(count,nullptr);buffers_.assign(count,std::vector<uint8_t>(bytes));in_flight_.assign(count,false);
  for(uint32_t k=0;k<count;++k){
    auto* t=libusb_alloc_transfer(static_cast<int>(packets));
    if (!t) {
      error_code = LIBUSB_ERROR_NO_MEM;
      return Status::failure(usb_error("libusb_alloc_transfer", error_code));
    }
    transfers_[k]=t;
    libusb_fill_iso_transfer(t,handle_,endpoint,buffers_[k].data(),static_cast<int>(bytes),static_cast<int>(packets),on_transfer,this,timeout);
    libusb_set_iso_packet_lengths(t,packet_bytes);
  }
  std::lock_guard<std::mutex> lock(transfers_mutex_);submitting_=true;
  for(size_t k=0;k<transfers_.size();++k){
    in_flight_[k]=true;++pending_; // Reserve before submission; rollback on failure.
    const int r=libusb_submit_transfer(transfers_[k]);
    if (r) {
      error_code = r;
      in_flight_[k] = false;
      --pending_;
      submitting_ = false;
      if (r == LIBUSB_ERROR_IO) startup_failure_ = StartupFailure::IsoSubmitIo;
      const auto error = usb_error("libusb_submit_transfer", r) +
          "; slot " + std::to_string(k + 1) + "/" + std::to_string(count) +
          ", endpoint=" + std::to_string(endpoint) + ", packets=" + std::to_string(packets) +
          ", bytes/packet=" + std::to_string(packet_bytes);
      log(error);
      return Status::failure(error);
    }
  }
  log("queued " + std::to_string(count) + " isochronous transfers, packets/transfer=" +
      std::to_string(packets) + ", bytes/transfer=" + std::to_string(bytes));
  return Status::success();
}
void Cs30LibusbSource::on_transfer(libusb_transfer* t){static_cast<Cs30LibusbSource*>(t->user_data)->handle_transfer(t);}
void Cs30LibusbSource::handle_transfer(libusb_transfer* t) {
  last_transfer_status_=static_cast<int>(t->status);
  if(t->status==LIBUSB_TRANSFER_COMPLETED)last_transfer_ns_=steady_ns();
  if(submitting_.load()&&t->status==LIBUSB_TRANSFER_COMPLETED){
    descs_.resize(static_cast<size_t>(t->num_iso_packets));
    for(int k=0;k<t->num_iso_packets;++k){const auto& d=t->iso_packet_desc[k];descs_[k]={d.length,d.actual_length,static_cast<int32_t>(d.status)};}
    engine_->push_iso_transfer(t->buffer,static_cast<size_t>(t->length),descs_.data(),descs_.size());
  } else if(t->status!=LIBUSB_TRANSFER_CANCELLED&&t->status!=LIBUSB_TRANSFER_COMPLETED){
    ++transfer_errors_;log("USB completion status="+std::to_string(static_cast<int>(t->status))+
        (t->status==LIBUSB_TRANSFER_NO_DEVICE?" (NO_DEVICE)":""));
  }
  std::lock_guard<std::mutex> lock(transfers_mutex_);
  const auto it=std::find(transfers_.begin(),transfers_.end(),t);
  if(it==transfers_.end()){++transfer_errors_;return;}
  const size_t slot=static_cast<size_t>(it-transfers_.begin());
  if(!in_flight_[slot]){++transfer_errors_;return;}
  if(t->status==LIBUSB_TRANSFER_NO_DEVICE){submitting_=false;streaming_=false;}
  if(submitting_.load()&&t->status!=LIBUSB_TRANSFER_NO_DEVICE&&t->status!=LIBUSB_TRANSFER_CANCELLED){
    const int r=libusb_submit_transfer(t);if(r==0)return; // Keep this slot's reservation.
    ++transfer_errors_;log(usb_error("resubmit transfer",r));if(r==LIBUSB_ERROR_NO_DEVICE){submitting_=false;streaming_=false;}
  }
  in_flight_[slot]=false;--pending_;
  if(pending_==0&&submitting_.load()){
    submitting_=false;streaming_=false;log("USB transfer queue exhausted; transport stopped");
  }
  drained_.notify_all();
}
Status Cs30LibusbSource::start(bool restore_stream_idle) {
  std::lock_guard<std::mutex> lifecycle(lifecycle_mutex_);
  startup_failure_ = StartupFailure::None;
  if(streaming_)return Status::success();
  {std::lock_guard<std::mutex> lock(transfers_mutex_);if(pending_||!transfers_.empty()||
      std::any_of(claimed_.begin(),claimed_.end(),[](bool claimed){return claimed;}))
      return Status::failure("Previous USB cleanup is incomplete; retry disconnect before reopening");}
  last_transfer_ns_=0;last_transfer_status_=0;
  engine_->reset_stream();prepare_configuration();Status status=claim(cs30::kControlInterface);
  if (status && wrapped_ && restore_stream_idle) {
    // A powered hub may leave the camera running when only its host cable is
    // unplugged. Restore the streaming interface before Probe and Commit.
    status = claim(cs30::kStreamingInterface);
    if (status) {
      const int r = libusb_set_interface_alt_setting(handle_, cs30::kStreamingInterface, 0);
      log("powered replug: restore stream interface 1 alt 0, result=" + std::to_string(r));
      if (r) {
        if (r == LIBUSB_ERROR_OTHER || r == LIBUSB_ERROR_IO) startup_failure_ = StartupFailure::StreamingAlt;
        status = Status::failure(usb_error("restore stream interface 1 alt 0 before startup", r));
      }
    }
  }
  for(size_t i=0;status&&i<Engine::startup_step_count();++i){
    const auto& step=Engine::startup_step(i);
    switch(step.kind){
      case cs30::StepKind::kControl:{
        std::vector<uint8_t> response(step.is_in()?step.length:0);
        auto* data=step.is_in()?response.data():const_cast<uint8_t*>(step.data);
        const int r=libusb_control_transfer(handle_,step.request_type,step.request,step.value,step.index,data,step.length,cs30::kControlTimeoutMs);
        if(r<0)status=Status::failure(usb_error("startup step "+std::to_string(i),r));
        else if(step.is_in())status=engine_->on_startup_response(i,response.data(),static_cast<size_t>(r));
        else if(r!=step.data_length)status=Status::failure("Short startup OUT response");
        break;
      }
      case cs30::StepKind::kSetAlt:
        status=claim(step.interface_number);
        if (status) {
          if (step.interface_number == cs30::kControlInterface && step.alt_setting == 0 &&
              control_alt_zero_only_) {
            log("startup interface 0 has only alt 0; skipping redundant SET_INTERFACE");
            break;
          }
          const int r = libusb_set_interface_alt_setting(handle_, step.interface_number, step.alt_setting);
          log("startup set interface=" + std::to_string(step.interface_number) +
              ", alt=" + std::to_string(step.alt_setting) + ", result=" + std::to_string(r));
          if (r) {
            if (step.interface_number == cs30::kStreamingInterface && step.alt_setting == 1 &&
                (r == LIBUSB_ERROR_OTHER || r == LIBUSB_ERROR_IO)) {
              startup_failure_ = StartupFailure::StreamingAlt;
            }
            status = Status::failure(usb_error("startup step " + std::to_string(i) +
                ", set interface " + std::to_string(step.interface_number) +
                " alt " + std::to_string(step.alt_setting), r));
          }
        }
        break;
      case cs30::StepKind::kQueueIso:
        status=queue_iso(cs30::kIsoEndpoint,step.iso_transfers,step.iso_transfer_bytes,step.iso_packets,step.iso_timeout_ms);
        // Start even on partial submit failure so cancellation completions can drain.
        start_events();break;
    }
    if(status&&step.settle_ms)std::this_thread::sleep_for(std::chrono::milliseconds(step.settle_ms));
  }
  if(status)status=engine_->finish_startup();
  if(status){std::lock_guard<std::mutex> lock(transfers_mutex_);if(pending_==0||!submitting_.load())status=Status::failure("USB transport stopped during startup; no active transfers remain");else streaming_=true;}
  if(!status){const auto error=status.message;const auto stopped=stop_locked();return Status::failure(error+(stopped?"":"; cleanup: "+stopped.message));}
  log("CS30 started; "+engine_->device_summary());return Status::success();
}
Status Cs30LibusbSource::release_all() {
  std::string errors;
  for(int i=static_cast<int>(claimed_.size())-1;i>=0;--i)if(claimed_[i]){
    const int r=libusb_release_interface(handle_,i);
    log("release interface="+std::to_string(i)+", result="+std::to_string(r));
    if(r==0||r==LIBUSB_ERROR_NO_DEVICE||r==LIBUSB_ERROR_NOT_FOUND)claimed_[i]=false;
    else errors+=usb_error("release interface "+std::to_string(i),r)+"; ";
  }
  return errors.empty()?Status::success():Status::failure(errors);
}
Status Cs30LibusbSource::drain_iso_queue_locked() {
  {
    std::unique_lock<std::mutex> lock(transfers_mutex_);submitting_=false;streaming_=false;
    const auto deadline=std::chrono::steady_clock::now()+std::chrono::seconds(3);
    while(pending_>0){
      for(size_t k=0;k<transfers_.size();++k)if(in_flight_[k]){
        const int r=libusb_cancel_transfer(transfers_[k]);
        if(r!=0&&r!=LIBUSB_ERROR_NOT_FOUND)log(usb_error("cancel transfer",r));
      }
      if(drained_.wait_until(lock,deadline,[this]{return pending_==0;}))break;
      const auto message="USB cancellation still pending ("+std::to_string(pending_)+"); retaining fd, buffers and event pump. Retry disconnect or unplug the camera.";
      log(message);return Status::failure(message);
    }
  }
  stop_events(); // Also joins a callback which has just dropped the final reservation.
  return Status::success();
}
void Cs30LibusbSource::free_iso_queue_locked() {
  for (auto* transfer : transfers_) {
    if (transfer) libusb_free_transfer(transfer);
  }
  transfers_.clear();
  buffers_.clear();
  in_flight_.clear();
}
Status Cs30LibusbSource::stop_locked() {
  const auto drained = drain_iso_queue_locked();
  if (!drained) return drained;
  std::string errors;
  for(int i=1;i>=0;--i)if(claimed_[i]){
    if (i == cs30::kControlInterface && control_alt_zero_only_) continue;
    // No ISO requests were queued if enabling the stream interface failed.
    // Release the claim directly so a timed-out SET_INTERFACE does not trigger another one.
    if (i == cs30::kStreamingInterface && startup_failure_ == StartupFailure::StreamingAlt) {
      log("releasing stream interface after failed alt selection");
      continue;
    }
    const int r=libusb_set_interface_alt_setting(handle_,i,0);
    log("stop set interface=" + std::to_string(i) + ", alt=0, result=" + std::to_string(r));
    if(r&&r!=LIBUSB_ERROR_NO_DEVICE)errors+=usb_error("stop set alt "+std::to_string(i),r)+"; ";
  }
  const auto released=release_all();
  if(!released)return released;
  if(!errors.empty())log(errors); // Successful release ends ownership even if alt 0 failed.
  free_iso_queue_locked();
  engine_->reset_stream();
  return Status::success();
}
Status Cs30LibusbSource::stop(){std::lock_guard<std::mutex> lock(lifecycle_mutex_);return stop_locked();}
Status Cs30LibusbSource::reset_device(){
  std::lock_guard<std::mutex> lock(lifecycle_mutex_);
  const auto stopped=stop_locked();if(!stopped)return stopped;
  const int r=libusb_reset_device(handle_);return r?Status::failure(usb_error("reset device",r)):Status::success();
}
Cs30LibusbSource::Recovery Cs30LibusbSource::reset_after_startup_error() {
  std::lock_guard<std::mutex> lock(lifecycle_mutex_);
  if (!wrapped_ || startup_failure_ == StartupFailure::None) return Recovery::Unavailable;
  const char* reason = startup_failure_ == StartupFailure::StreamingAlt ?
      "stream interface alt selection" : "initial submit I/O";
  const auto stopped = stop_locked();
  startup_failure_ = StartupFailure::None;
  if (!stopped) {
    log("Cannot reset before USB cleanup: " + stopped.message);
    return Recovery::Unavailable;
  }
  const int reset = libusb_reset_device(handle_);
  if (reset == LIBUSB_ERROR_NOT_FOUND || reset == LIBUSB_ERROR_NO_DEVICE) {
    log(usb_error("USB reset invalidated the old device; rediscover", reset));
    return Recovery::Rediscover;
  }
  if (reset != 0) {
    log(usb_error(std::string("USB reset after ") + reason, reset));
    return Recovery::Unavailable;
  }
  log(std::string("USB reset after ") + reason + " succeeded; reopen with a fresh platform fd");
  return Recovery::Reopen;
}
}
