#include "harmony_usb_transport.h"
#include <algorithm>
#include <chrono>
#include <cstring>
#include <exception>
#include <utility>

namespace lingtouch {
HarmonyUsbBridge::HarmonyUsbBridge() {receiver_=std::thread([this]{receive_loop();});}
HarmonyUsbBridge::~HarmonyUsbBridge() {
  abort();
  {std::lock_guard<std::mutex> lock(queue_mutex_);shutting_down_=true;}
  queued_.notify_all();
  if(receiver_.joinable())receiver_.join();
}
void HarmonyUsbBridge::set_dispatcher(Dispatcher dispatcher) {
  std::lock_guard<std::mutex> lock(mutex_);dispatcher_=std::move(dispatcher);aborted_=false;
}
CameraStatus HarmonyUsbBridge::execute(HarmonyUsbCommand command,HarmonyUsbReply& reply) {
  Dispatcher dispatch;
  {
    std::lock_guard<std::mutex> lock(mutex_);
    if(aborted_ || !dispatcher_)return {CameraCode::kDisconnected,"鸿蒙 USB 服务未就绪"};
    if(waiting_id_)return {CameraCode::kInvalidState,"USB 操作必须串行执行"};
    command.request_id=next_id_++;waiting_id_=command.request_id;done_=false;dispatch=dispatcher_;
  }
  if(!dispatch(command)) {
    std::lock_guard<std::mutex> lock(mutex_);waiting_id_=0;
    return {CameraCode::kIoError,"无法把 USB 操作交给系统线程"};
  }
  std::unique_lock<std::mutex> lock(mutex_);
  const auto wait=std::chrono::milliseconds(std::max<uint32_t>(20000,command.control.timeout_ms+5000));
  if(!ready_.wait_for(lock,wait,[&]{return done_ || aborted_;})) {
    waiting_id_=0;return {CameraCode::kIoError,"等待系统 USB 操作完成超时"};
  }
  waiting_id_=0;
  if(aborted_)return {CameraCode::kDisconnected,"系统 USB 服务已关闭"};
  if(result_)reply=std::move(reply_);
  return result_;
}
void HarmonyUsbBridge::complete(uint64_t id,CameraStatus status,HarmonyUsbReply reply) {
  std::lock_guard<std::mutex> lock(mutex_);
  if(id!=waiting_id_ || done_ || aborted_)return;
  result_=std::move(status);reply_=std::move(reply);done_=true;ready_.notify_all();
}
void HarmonyUsbBridge::abort() {
  {std::lock_guard<std::mutex> lock(mutex_);aborted_=true;dispatcher_={};ready_.notify_all();}
  set_sinks(0,{},{});
}
void HarmonyUsbBridge::set_sinks(uint64_t epoch,CameraUsbTransport::PacketSink packets,CameraUsbTransport::EventSink events,
                                 size_t transfer_bytes) {
  // Barrier for the executing callback; the queue mutex is never held while
  // invoking client code. Late transfers are discarded by epoch.
  std::lock_guard<std::mutex> delivery(delivery_);
  std::lock_guard<std::mutex> lock(queue_mutex_);
  epoch_=queued_epoch_=epoch;packets_=std::move(packets);events_=std::move(events);
  accepting_=bool(packets_);head_=queued_count_=0;queued_event_.reset();
  if(accepting_) {
    transfer_bytes_=std::min(transfer_bytes,size_t(128*3072));
    for(auto& batch:queue_)batch.bytes.resize(transfer_bytes_);
    high_water_=0;overflows_=0;
  }
}
void HarmonyUsbBridge::push_packets(uint64_t epoch,const uint8_t* p,size_t n,const IsoPacketDesc* d,size_t count) {
  std::lock_guard<std::mutex> lock(queue_mutex_);
  if(epoch!=queued_epoch_ || !accepting_)return;
  if(queued_count_==kQueueCapacity || n>transfer_bytes_ || count>128) {
    ++overflows_;accepting_=false;queued_count_=0;
    queued_event_=CameraStatus{CameraCode::kStreamInterrupted,"原生接收队列已满或批次越界，已停止当前会话以避免损坏图像"};
  } else {
    auto& batch=queue_[(head_+queued_count_)%kQueueCapacity];
    if(n)std::memcpy(batch.bytes.data(),p,n);
    if(count)std::copy(d,d+count,batch.descs.begin());
    batch.size=n;batch.count=count;++queued_count_;
    high_water_=std::max(high_water_,queued_count_);
  }
  queued_.notify_one();
}
void HarmonyUsbBridge::push_event(uint64_t epoch,const CameraStatus& status) {
  std::lock_guard<std::mutex> lock(queue_mutex_);
  if(epoch!=queued_epoch_ || !accepting_)return;
  accepting_=false;queued_count_=0;queued_event_=status;queued_.notify_one();
}
std::string HarmonyUsbBridge::receive_diagnostics() const {
  std::lock_guard<std::mutex> lock(queue_mutex_);
  return "原生接收队列 "+std::to_string(queued_count_)+"/"+std::to_string(kQueueCapacity)+
      "，峰值 "+std::to_string(high_water_)+"，溢出 "+std::to_string(overflows_);
}
void HarmonyUsbBridge::receive_loop() {
  Batch batch;batch.bytes.resize(128*3072);
  for(;;) {
    uint64_t epoch=0;std::optional<CameraStatus> event;
    {
      std::unique_lock<std::mutex> lock(queue_mutex_);
      queued_.wait(lock,[this]{return shutting_down_ || queued_event_ || queued_count_>0;});
      if(shutting_down_)return;
      epoch=queued_epoch_;
      if(queued_event_){event=std::move(queued_event_);queued_event_.reset();}
      else {
        const auto& source=queue_[head_];batch.size=source.size;batch.count=source.count;
        if(batch.size)std::memcpy(batch.bytes.data(),source.bytes.data(),batch.size);
        std::copy(source.descs.begin(),source.descs.begin()+batch.count,batch.descs.begin());
        head_=(head_+1)%kQueueCapacity;--queued_count_;
      }
    }
    std::lock_guard<std::mutex> delivery(delivery_);
    if(epoch!=epoch_)continue;
    try {
      if(event){if(events_)events_(*event);}
      else if(packets_)packets_(batch.bytes.data(),batch.size,batch.descs.data(),batch.count);
    } catch(const std::exception& error) {
      if(events_)events_({CameraCode::kStreamInterrupted,std::string("原生接收处理失败：")+error.what()});
      std::lock_guard<std::mutex> lock(queue_mutex_);accepting_=false;queued_count_=0;
    }
  }
}
HarmonyUsbTransport::~HarmonyUsbTransport(){close();}
CameraStatus HarmonyUsbTransport::run(HarmonyUsbCommand command) {HarmonyUsbReply reply;return bridge_->execute(std::move(command),reply);}
CameraStatus HarmonyUsbTransport::enumerate(std::vector<CameraUsbDevice>& devices) {
  HarmonyUsbReply reply;auto s=bridge_->execute({},reply);if(s)devices=std::move(reply.devices);return s;
}
CameraStatus HarmonyUsbTransport::open(const std::string& id) {
  if(opened_)return {CameraCode::kInvalidState,"USB 已打开"};
  HarmonyUsbCommand command;command.operation=HarmonyUsbOperation::kOpen;command.device_id=id;
  auto status=run(command);
  if(status)opened_=true;
  else {
    // A timed-out system open can complete late. Queue its cleanup behind it.
    HarmonyUsbCommand cleanup;cleanup.operation=HarmonyUsbOperation::kClose;run(cleanup);
  }
  return status;
}
CameraStatus HarmonyUsbTransport::claim(int id) {
  HarmonyUsbCommand c;c.operation=HarmonyUsbOperation::kClaim;c.interface_number=id;return run(c);
}
CameraStatus HarmonyUsbTransport::set_alt(int id,int alt) {
  HarmonyUsbCommand c;c.operation=HarmonyUsbOperation::kSetAlt;c.interface_number=id;c.alternate=alt;return run(c);
}
CameraStatus HarmonyUsbTransport::control(const CameraUsbControl& request,std::vector<uint8_t>& response) {
  HarmonyUsbCommand c;c.operation=HarmonyUsbOperation::kControl;c.control=request;
  HarmonyUsbReply reply;auto s=bridge_->execute(std::move(c),reply);if(s)response=std::move(reply.data);return s;
}
CameraStatus HarmonyUsbTransport::start_iso(const CameraIsoConfig& iso,PacketSink packets,EventSink events) {
  ++epoch_;bridge_->set_sinks(epoch_,std::move(packets),std::move(events),size_t(iso.packet_bytes)*iso.packets);
  HarmonyUsbCommand c;c.operation=HarmonyUsbOperation::kStartIso;c.iso=iso;c.epoch=epoch_;
  const auto status=run(c);
  // A partial submit failure also needs cancellation of successfully submitted requests.
  streaming_=true;
  if(!status)stop_iso();
  return status;
}
CameraStatus HarmonyUsbTransport::stop_iso() {
  bridge_->set_sinks(++epoch_,{},{});
  if(!streaming_)return {};
  HarmonyUsbCommand c;c.operation=HarmonyUsbOperation::kStopIso;
  auto status=run(c);if(status)streaming_=false;return status;
}
CameraStatus HarmonyUsbTransport::close() {
  auto stopped=stop_iso();
  if(!opened_)return stopped;
  HarmonyUsbCommand c;c.operation=HarmonyUsbOperation::kClose;
  auto status=run(c);if(status)opened_=false;return stopped?status:stopped;
}
} // namespace lingtouch
