#include "android_usb_transport.h"
#include <libusb.h>
#include <algorithm>
#include <atomic>
#include <thread>
#include <utility>

namespace lingtouch {
namespace {
CameraStatus usb_status(const std::string& operation,int error) {
  if (error>=0) return {};
  CameraCode code=CameraCode::kIoError;
  if (error==LIBUSB_ERROR_ACCESS) code=CameraCode::kPermissionDenied;
  if (error==LIBUSB_ERROR_NO_DEVICE) code=CameraCode::kDisconnected;
  return {code,operation+"："+libusb_error_name(error)+" ("+std::to_string(error)+")"};
}
}
struct AndroidUsbTransport::Impl {
  struct Slot {
    Impl* owner=nullptr;
    libusb_transfer* transfer=nullptr;
    std::vector<uint8_t> bytes;
    std::vector<IsoPacketDesc> packets;
    bool in_flight=false;
    ~Slot(){if(transfer)libusb_free_transfer(transfer);}
  };
  AndroidUsbHost host;
  libusb_context* context=nullptr;
  libusb_device_handle* device=nullptr;
  std::vector<int> claimed;
  std::vector<std::unique_ptr<Slot>> slots;
  std::thread events;
  std::mutex io_mutex;
  std::condition_variable drained;
  std::atomic<bool> events_running{false};
  bool submitting=false;
  size_t pending=0;
  PacketSink sink;
  EventSink error;
  explicit Impl(AndroidUsbHost h):host(std::move(h)){}

  static void LIBUSB_CALL callback(libusb_transfer* transfer) {
    auto* slot=static_cast<Slot*>(transfer->user_data);
    Impl& self=*slot->owner;
    bool fatal=false;
    if(transfer->status==LIBUSB_TRANSFER_COMPLETED) {
      if(transfer->num_iso_packets!=int(slot->packets.size()) || transfer->length!=int(slot->bytes.size())) {
        fatal=true;
        if(self.error)self.error({CameraCode::kStreamInterrupted,"USB 回调的包数或缓冲区长度与请求不符"});
      } else {
        const uint32_t stride=uint32_t(slot->bytes.size()/slot->packets.size());
        for(size_t i=0;i<slot->packets.size();++i) {
          const auto& p=transfer->iso_packet_desc[i];
          // JNI does not have Harmony's TypedArray length-unit difference.
          // Still validate native descriptors and preserve the original stride
          // so one bad packet cannot shift subsequent packet addresses.
          const bool valid=p.length==stride && p.actual_length<=stride;
          slot->packets[i]={stride,valid?p.actual_length:0,valid?int32_t(p.status):int32_t(LIBUSB_TRANSFER_ERROR)};
        }
        if(self.sink) self.sink(transfer->buffer,slot->bytes.size(),slot->packets.data(),slot->packets.size());
      }
    } else if(transfer->status==LIBUSB_TRANSFER_NO_DEVICE) {
      fatal=true;
      if(self.error)self.error({CameraCode::kDisconnected,"USB 设备已断开"});
    } else if(transfer->status!=LIBUSB_TRANSFER_CANCELLED && transfer->status!=LIBUSB_TRANSFER_TIMED_OUT) {
      fatal=true;
      if(self.error)self.error({CameraCode::kStreamInterrupted,"USB 等时接收失败，状态 "+std::to_string(transfer->status)});
    }
    CameraStatus submit_error;
    {
      std::lock_guard<std::mutex> lock(self.io_mutex);
      if(self.submitting && !fatal && transfer->status!=LIBUSB_TRANSFER_CANCELLED) {
        const int result=libusb_submit_transfer(transfer);
        if(result==0)return;
        submit_error=usb_status("重新提交等时接收",result);
      }
      if(fatal || !submit_error)self.submitting=false;
    }
    if(!submit_error && self.error)self.error(submit_error);
    // Decrement only after all sinks have returned; stop must drain callbacks,
    // not just kernel requests, before the session or Java fd can be destroyed.
    {
      std::lock_guard<std::mutex> lock(self.io_mutex);
      slot->in_flight=false;--self.pending;self.drained.notify_all();
    }
  }
};

AndroidUsbTransport::AndroidUsbTransport(AndroidUsbHost host):impl_(std::make_unique<Impl>(std::move(host))){}
AndroidUsbTransport::~AndroidUsbTransport(){close();}
CameraStatus AndroidUsbTransport::enumerate(std::vector<CameraUsbDevice>& out){return impl_->host.enumerate(out);}
CameraStatus AndroidUsbTransport::open(const std::string& id) {
  auto& s=*impl_;
  if(s.device)return {CameraCode::kInvalidState,"USB 已打开"};
  int fd=-1;
  auto status=s.host.open_fd(id,fd);
  if(!status)return status;
  if(fd<0){s.host.close_fd();return {CameraCode::kOpenFailed,"系统没有提供有效 USB 连接"};}
  libusb_init_option option{};option.option=LIBUSB_OPTION_NO_DEVICE_DISCOVERY;
  int result=libusb_init_context(&s.context,&option,1);
  if(result==0)result=libusb_wrap_sys_device(s.context,intptr_t(fd),&s.device);
  if(result!=0){close();return usb_status("打开已授权 USB 连接",result);}
  libusb_set_auto_detach_kernel_driver(s.device,0); // System force-claim owns driver handoff.
  libusb_device_descriptor descriptor{};
  result=libusb_get_device_descriptor(libusb_get_device(s.device),&descriptor);
  if(result!=0 || descriptor.idVendor!=cs30::kVendorId || descriptor.idProduct!=cs30::kProductId) {
    close();return {CameraCode::kOpenFailed,"USB 描述符不是 CS30"};
  }
  const int speed=libusb_get_device_speed(libusb_get_device(s.device));
  if(speed!=LIBUSB_SPEED_UNKNOWN && speed<LIBUSB_SPEED_HIGH){close();return {CameraCode::kOpenFailed,"CS30 需要 USB 高速主机连接，请检查 OTG、线材和供电"};}
  if(s.host.log)s.host.log("USB 已授权打开；速度代码 "+std::to_string(speed));
  return {};
}
CameraStatus AndroidUsbTransport::claim(int id) {
  auto& s=*impl_;
  if(!s.device)return {CameraCode::kInvalidState,"USB 尚未打开"};
  if(std::find(s.claimed.begin(),s.claimed.end(),id)!=s.claimed.end())return {};
  const int result=libusb_claim_interface(s.device,id);
  if(result==0)s.claimed.push_back(id);
  return usb_status("接管 USB 接口",result);
}
CameraStatus AndroidUsbTransport::set_alt(int id,int alt) {
  if(!impl_->device)return {CameraCode::kInvalidState,"USB 尚未打开"};
  // Stopping before the first start need not claim the streaming interface.
  if(alt==0 && std::find(impl_->claimed.begin(),impl_->claimed.end(),id)==impl_->claimed.end())return {};
  return usb_status("设置 USB alternate",libusb_set_interface_alt_setting(impl_->device,id,alt));
}
CameraStatus AndroidUsbTransport::control(const CameraUsbControl& request,std::vector<uint8_t>& out) {
  if(!impl_->device)return {CameraCode::kInvalidState,"USB 尚未打开"};
  const bool in=(request.request_type&0x80)!=0;
  if(!in && request.data.size()!=request.length)return {CameraCode::kIoError,"控制请求长度不匹配"};
  auto data=in?std::vector<uint8_t>(request.length):request.data;
  const int n=libusb_control_transfer(impl_->device,request.request_type,request.request,request.value,
      request.index,data.data(),request.length,request.timeout_ms);
  if(n<0)return usb_status("USB 控制请求 0x"+std::to_string(request.value),n);
  if((!in && n!=request.length) || (in && n==0 && request.length))return {CameraCode::kIoError,"USB 控制请求返回长度异常"};
  if(in){data.resize(size_t(n));out=std::move(data);} else out.clear();
  return {};
}
CameraStatus AndroidUsbTransport::start_iso(const CameraIsoConfig& config,PacketSink sink,EventSink error) {
  auto& s=*impl_;
  if(!s.device || !s.slots.empty())return {CameraCode::kInvalidState,"USB 接收状态不正确"};
  if(config.transfers==0 || config.transfers>32 || config.packets==0 || config.packets>128 ||
      config.packet_bytes==0 || config.packet_bytes>3072)return {CameraCode::kStartFailed,"USB 接收队列参数不正确"};
  const int packet_capacity=libusb_get_max_iso_packet_size(libusb_get_device(s.device),config.endpoint);
  if(packet_capacity<0 || uint32_t(packet_capacity)<config.packet_bytes)
    return {CameraCode::kUnsupportedProfile,"设备等时端点容量不足"};
  uint32_t packets=std::min(config.packets,8u);
  for(;;) {
    s.sink=sink;s.error=error;
    if(s.host.log)s.host.log("USB 每请求 "+std::to_string(packets*config.packet_bytes)+" B（"+
        std::to_string(packets)+" 包），并行 "+std::to_string(config.transfers));
    for(uint32_t i=0;i<config.transfers;++i) {
      auto slot=std::make_unique<Impl::Slot>();slot->owner=&s;
      slot->bytes.resize(size_t(packets)*config.packet_bytes);slot->packets.resize(packets);
      slot->transfer=libusb_alloc_transfer(int(packets));
      if(!slot->transfer){stop_iso();return {CameraCode::kStartFailed,"无法分配等时请求"};}
      libusb_fill_iso_transfer(slot->transfer,s.device,config.endpoint,slot->bytes.data(),int(slot->bytes.size()),
          int(packets),Impl::callback,slot.get(),config.timeout_ms);
      libusb_set_iso_packet_lengths(slot->transfer,config.packet_bytes);
      s.slots.push_back(std::move(slot));
    }
    s.events_running=true;
    s.events=std::thread([&s]{
      while(s.events_running) {
        timeval wait{0,100000};
        const int result=libusb_handle_events_timeout_completed(s.context,&wait,nullptr);
        if(result<0 && result!=LIBUSB_ERROR_INTERRUPTED && s.host.log)
          s.host.log("libusb 事件："+std::string(libusb_error_name(result)));
      }
    });
    int result=0;
    {
      std::lock_guard<std::mutex> lock(s.io_mutex);s.submitting=true;
      for(auto& slot:s.slots) {
        ++s.pending;slot->in_flight=true;
        result=libusb_submit_transfer(slot->transfer);
        if(result!=0){--s.pending;slot->in_flight=false;break;}
      }
    }
    if(result==0)return {};
    const auto failed=usb_status("提交等时接收",result);
    // Drain the real callbacks before changing request size or freeing buffers.
    stop_iso();
    if(s.host.log)s.host.log(failed.message);
    if(packets==1 || (result!=LIBUSB_ERROR_IO && result!=LIBUSB_ERROR_NO_MEM))return failed;
    packets=std::max(1u,packets/2);
  }
}
CameraStatus AndroidUsbTransport::stop_iso() {
  auto& s=*impl_;
  {
    std::unique_lock<std::mutex> lock(s.io_mutex);s.submitting=false;
    for(const auto& slot:s.slots)if(slot->in_flight)libusb_cancel_transfer(slot->transfer);
    s.drained.wait(lock,[&]{return s.pending==0;});
  }
  s.events_running=false;
  if(s.context)libusb_interrupt_event_handler(s.context);
  if(s.events.joinable())s.events.join();
  s.slots.clear();s.sink={};s.error={};return {};
}
CameraStatus AndroidUsbTransport::close() {
  auto& s=*impl_;stop_iso();
  if(s.device) {
    for(auto it=s.claimed.rbegin();it!=s.claimed.rend();++it)libusb_release_interface(s.device,*it);
    libusb_close(s.device);s.device=nullptr;
  }
  s.claimed.clear();
  if(s.context){libusb_exit(s.context);s.context=nullptr;}
  s.host.close_fd();return {};
}
} // namespace lingtouch
