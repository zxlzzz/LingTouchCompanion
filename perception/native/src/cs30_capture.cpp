#include "lingtouch/perception/cs30_capture.h"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <sstream>
#include <utility>

#include "lingtouch/perception/cs30_calibration.h"

namespace lingtouch {
namespace {
CameraStatus fail(CameraCode code, std::string message) { return {code, std::move(message)}; }
int64_t now_ns() {
  return std::chrono::duration_cast<std::chrono::nanoseconds>(
      std::chrono::steady_clock::now().time_since_epoch()).count();
}
bool same(const CameraStreamProfile& a, const CameraStreamProfile& b) {
  return a.mode == b.mode && a.depth.width == b.depth.width && a.depth.height == b.depth.height &&
         a.color.has_value() == b.color.has_value() &&
         (!a.color || (a.color->width == b.color->width && a.color->height == b.color->height));
}
uint32_t le32(const uint8_t* p) {
  return uint32_t(p[0]) | uint32_t(p[1]) << 8 | uint32_t(p[2]) << 16 | uint32_t(p[3]) << 24;
}
void put16(std::vector<uint8_t>& p, size_t offset, int value) {
  p[offset] = static_cast<uint8_t>(value);
  p[offset + 1] = static_cast<uint8_t>(value >> 8);
}
// Validate JPEG framing and its encoded dimensions without decoding pixels.
bool jpeg_size(const uint8_t* p, size_t size, CameraResolution expected) {
  if (size < 4 || p[0] != 0xff || p[1] != 0xd8 || p[size-2] != 0xff || p[size-1] != 0xd9) return false;
  size_t at = 2;
  while (at + 4 <= size) {
    if (p[at++] != 0xff) return false;
    while (at < size && p[at] == 0xff) ++at;
    if (at >= size) return false;
    const uint8_t marker = p[at++];
    if (marker == 0xda || marker == 0xd9) return false;
    if (marker == 0x01 || (marker >= 0xd0 && marker <= 0xd7)) continue;
    if (size - at < 2) return false;
    const size_t n = size_t(p[at]) * 256 + p[at+1];
    if (n < 2 || n > size - at) return false;
    if (marker == 0xc0 || marker == 0xc1 || marker == 0xc2) {
      return n >= 8 && int(p[at+3]) * 256 + p[at+4] == expected.height &&
             int(p[at+5]) * 256 + p[at+6] == expected.width;
    }
    at += n;
  }
  return false;
}
bool valid_intrinsics(const CameraIntrinsics& in) {
  const double v[] = {in.fx,in.fy,in.cx,in.cy,in.k1,in.k2,in.k3,in.p1,in.p2};
  return in.width > 0 && in.height > 0 && in.fx > 0 && in.fy > 0 && in.cx >= 0 && in.cy >= 0 &&
         in.cx < in.width && in.cy < in.height &&
         std::all_of(std::begin(v),std::end(v),[](double x){return std::isfinite(x);});
}
bool valid_rotation(const std::array<double,9>& r) {
  for (double x : r) if (!std::isfinite(x)) return false;
  for (int i=0;i<3;++i) for (int j=0;j<3;++j) {
    double dot=0;for(int k=0;k<3;++k) dot+=r[3*i+k]*r[3*j+k];
    if (std::abs(dot-(i==j?1.0:0.0))>0.02) return false;
  }
  const double det=r[0]*(r[4]*r[8]-r[5]*r[7])-r[1]*(r[3]*r[8]-r[5]*r[6])+r[2]*(r[3]*r[7]-r[4]*r[6]);
  return std::abs(det-1.0)<0.02;
}
}  // namespace

Cs30CaptureSession::Cs30CaptureSession(std::unique_ptr<CameraUsbTransport> transport,
                                     FrameSink frame_sink, ResetSink reset_sink)
    : transport_(std::move(transport)), frame_sink_(std::move(frame_sink)), reset_sink_(std::move(reset_sink)) {}
Cs30CaptureSession::~Cs30CaptureSession() { close_device(); }

CameraStatus Cs30CaptureSession::find_devices(std::vector<std::string>& ids) {
  std::vector<CameraUsbDevice> devices;
  CameraStatus status=transport_->enumerate(devices);
  if (!status) return status;
  std::vector<std::string> found;
  for (const auto& device:devices) if (!device.id.empty()) found.push_back(device.id);
  enumerated_ids_=found;
  ids=std::move(found);
  return {};
}

CameraStatus Cs30CaptureSession::open_device(const std::string& id, SensorAdapter::EventCallback callback) {
  if (opened_) return fail(CameraCode::kInvalidState,"设备已经打开，请先关闭");
  if (std::find(enumerated_ids_.begin(),enumerated_ids_.end(),id)==enumerated_ids_.end())
    return fail(CameraCode::kDeviceNotFound,"设备 ID 不属于最近一次枚举，请重新查找");
  CameraStatus status=transport_->open(id);
  if (!status) return status;
  status=transport_->claim(cs30::kControlInterface);
  if (!status) { transport_->close(); return status; }
  std::lock_guard<std::mutex> lock(mutex_);
  opened_=true;device_id_=id;callback_=std::move(callback);terminal_={};notified_=false;
  return {};
}

CameraStatus Cs30CaptureSession::get_stream_profiles(std::vector<CameraStreamProfile>& profiles) {
  std::lock_guard<std::mutex> lock(mutex_);
  if (!opened_) return fail(CameraCode::kInvalidState,"设备尚未打开");
  if (!terminal_) return terminal_;
  // SDK 4.2.5.0 CS30 QueryDeviceSupportResolution: depth 320/640,
  // RGB 640x480,960x540,1920x1080. Only aspect-preserving RGB sizes are
  // exposed here: the blob's RGB reference is 1920x1080, not a 4:3 image.
  std::vector<CameraStreamProfile> out;
  for (const auto d : {CameraResolution{640,480}, CameraResolution{320,240}}) {
    out.push_back({CameraStreamMode::kDepth,d,std::nullopt});
    out.push_back({CameraStreamMode::kDepthRgb,d,CameraResolution{960,540}});
    out.push_back({CameraStreamMode::kDepthRgb,d,CameraResolution{1920,1080}});
  }
  profiles=std::move(out);
  return {};
}

void Cs30CaptureSession::clear_stream_locked() {
  ++session_;accepting_=false;active_=false;latest_.reset();calibration_.reset();
  settings_={};collector_.reset();assembler_.reset();transfers_=0;rejected_payloads_=0;
}

CameraStatus Cs30CaptureSession::start_streaming(const CameraStreamProfile& profile) {
  {
    std::lock_guard<std::mutex> lock(mutex_);
    if (!opened_ || active_) return fail(CameraCode::kInvalidState,"需要已打开且已停止的设备");
    if (terminal_.code==CameraCode::kDisconnected) return terminal_;
  }
  std::vector<CameraStreamProfile> supported;
  CameraStatus status=get_stream_profiles(supported);
  if (!status) return status;
  if (std::none_of(supported.begin(),supported.end(),[&](const auto& x){return same(x,profile);}))
    return fail(CameraCode::kUnsupportedProfile,"该深度/彩色分辨率组合尚不支持");
  {
    std::lock_guard<std::mutex> lock(mutex_);
    clear_stream_locked();profile_=profile;terminal_={};notified_=false;active_=true;
  }
  if (reset_sink_) reset_sink_();
  status=execute_startup();
  if (!status) {
    stop_streaming();
    if (status.code==CameraCode::kIoError) status.code=CameraCode::kStartFailed;
    return status;
  }
  // Missing calibration is reported by get_calibration/get_latest_frame; it is
  // distinct from failure to submit the USB stream.
  load_calibration();
  {
    std::lock_guard<std::mutex> lock(mutex_);
    status=terminal_;
  }
  if(!status){stop_streaming();return status;}
  {
    std::lock_guard<std::mutex> lock(mutex_);
    last_frame_ns_=now_ns();monitoring_=true;
  }
  const uint64_t token=session_;
  monitor_=std::thread([this,token] {
    std::unique_lock<std::mutex> lock(mutex_);
    while (monitoring_) {
      monitor_cv_.wait_for(lock,std::chrono::milliseconds(250),[&]{return !monitoring_;});
      if (!monitoring_) break;
      if (accepting_ && now_ns()-last_frame_ns_>5000000000LL) {
        lock.unlock();
        on_event(token,fail(CameraCode::kStreamInterrupted,"5 秒没有完整的新帧；请核对固件、供电和 USB 日志"));
        return;
      }
    }
  });
  return {};
}

CameraStatus Cs30CaptureSession::execute_startup() {
  std::vector<uint8_t> probe;
  for (size_t i=0;i<cs30::startup_step_count();++i) {
    const auto& step=cs30::startup_steps()[i];
    CameraStatus status;
    if (step.kind==cs30::StepKind::kSetAlt) {
      status=transport_->claim(step.interface_number);
      if (status) status=transport_->set_alt(step.interface_number,step.alt_setting);
    } else if (step.kind==cs30::StepKind::kQueueIso) {
      const size_t depth_bytes=size_t(profile_.depth.width)*profile_.depth.height*2;
      const bool rgb=profile_.mode==CameraStreamMode::kDepthRgb;
      // Use the device's negotiated bound, with a hard allocation limit.
      const size_t fallback=rgb ? depth_bytes+size_t(profile_.color->width)*profile_.color->height*2+4096 : depth_bytes;
      const size_t negotiated=probe.size()>=22 ? le32(probe.data()+18) : 0;
      // CS30's UVC envelope can still describe 640x480 while vendor SetFormat
      // selects a larger composite payload. Never truncate RGB to that envelope.
      max_payload_bytes_=rgb ? std::max(fallback,negotiated) : depth_bytes;
      if (negotiated>8*1024*1024 || max_payload_bytes_>8*1024*1024)
        return fail(CameraCode::kUnsupportedProfile,"相机协商的帧大小与请求的流配置不符");
      {
        std::lock_guard<std::mutex> lock(mutex_);
        assembler_=std::make_unique<UvcFrameAssembler>(max_payload_bytes_,
            [this](const uint8_t* p,size_t n){on_payload(p,n);},rgb);
        accepting_=true;
      }
      const uint64_t token=session_;
      CameraIsoConfig config;
      config.transfers=step.iso_transfers;config.packets=step.iso_packets;
      config.packet_bytes=step.iso_transfer_bytes/step.iso_packets;config.timeout_ms=step.iso_timeout_ms;
      status=transport_->start_iso(config,
          [this,token](const uint8_t* p,size_t n,const IsoPacketDesc* d,size_t count){on_packets(token,p,n,d,count);},
          [this,token](const CameraStatus& event){on_event(token,event);});
    } else {
      CameraUsbControl request;
      request.request_type=step.request_type;request.request=step.request;
      request.value=step.value;request.index=step.index;request.length=step.length;
      if (step.data_length) request.data.assign(step.data,step.data+step.data_length);
      if (!step.is_in() && step.value==0xa100) {
        // Exact five-slot packing from CS30 SetFormat, not SDK enum ordinals:
        // [RAW, DEPTH, IR, RGB, AI], each LE16 width/height + one wire type.
        request.data.assign(25,0);
        put16(request.data,5,profile_.depth.width);put16(request.data,7,profile_.depth.height);request.data[9]=2;
        if (profile_.color) {
          put16(request.data,15,profile_.color->width);put16(request.data,17,profile_.color->height);request.data[19]=3;
        }
      }
      if (!step.is_in() && step.value==0x0200 && step.index==1) {
        if (probe.size()!=step.length) return fail(CameraCode::kStartFailed,"UVC Probe 响应长度不正确");
        request.data=probe; // Commit what this device actually negotiated.
      }
      std::vector<uint8_t> response;
      status=transport_->control(request,response);
      if (status && step.is_in()) {
        if (step.value==0x0100 && step.index==1 && step.request==0x81) probe=response;
        std::lock_guard<std::mutex> lock(mutex_);
        const Status parsed=collector_.on_response(i,response.data(),response.size());
        if (!parsed) status=fail(CameraCode::kStartFailed,parsed.message);
      }
    }
    if (!status) {status.message="启动步骤 "+std::to_string(i)+"："+status.message;return status;}
    if (step.settle_ms) std::this_thread::sleep_for(std::chrono::milliseconds(step.settle_ms));
  }
  return {};
}

CameraStatus Cs30CaptureSession::load_calibration() {
  cs30::DeviceInfo info;
  {std::lock_guard<std::mutex> lock(mutex_);info=collector_.info();}
  std::shared_ptr<CameraCalibration> result;
  for (int i=0;i<2;++i) {
    if (!info.calibration_complete[i]) continue;
    const auto& bytes=info.calibration[i];
    auto decoded=cs30::decode_calibration(bytes.data(),bytes.size());
    if (!decoded) continue;
    const auto& c=decoded.value();
    if (c.depth.width!=profile_.depth.width || c.depth.height!=profile_.depth.height || !valid_intrinsics(c.depth)) continue;
    auto candidate=std::make_shared<CameraCalibration>();candidate->depth=c.depth;
    if (profile_.color) {
      if (!c.has_rgb || !valid_rotation(c.rgb_from_depth_rotation)) continue;
      CameraColorCalibration color;
      color.intrinsics=c.rgb;
      // CS30 RGB blob reference is 1920x1080. Keep the existing 'inferred'
      // provenance until compared with GetIntric on the actual camera.
      const double scale=profile_.color->width/1920.0;
      color.intrinsics.width=profile_.color->width;color.intrinsics.height=profile_.color->height;
      color.intrinsics.fx*=scale;color.intrinsics.fy*=scale;
      color.intrinsics.cx*=scale;color.intrinsics.cy*=scale;
      color.intrinsics.id += ":"+std::to_string(profile_.color->width)+"x"+std::to_string(profile_.color->height);
      color.rgb_from_depth_rotation=c.rgb_from_depth_rotation;
      color.rgb_from_depth_translation_mm=c.rgb_from_depth_translation;
      if (!valid_intrinsics(color.intrinsics) || std::any_of(c.rgb_from_depth_translation.begin(),
          c.rgb_from_depth_translation.end(),[](double v){return !std::isfinite(v)||std::abs(v)>1000;})) continue;
      candidate->color=color;
    }
    result=std::move(candidate);break;
  }
  if (!result) return fail(CameraCode::kCalibrationUnavailable,"当前流的完整标定不可用");
  std::lock_guard<std::mutex> delivery(delivery_mutex_);
  std::lock_guard<std::mutex> lock(mutex_);
  calibration_=std::move(result);
  return {};
}

void Cs30CaptureSession::on_payload(const uint8_t* p,size_t size) {
  const size_t pixels=size_t(profile_.depth.width)*profile_.depth.height;
  const size_t depth_bytes=pixels*2;
  if (size<depth_bytes) {++rejected_payloads_;return;}
  FrameBundle frame;
  if (profile_.color) {
    if (size-depth_bytes<4) {++rejected_payloads_;return;}
    const size_t jpeg_bytes=le32(p+depth_bytes);
    if (jpeg_bytes>size-depth_bytes-4 || !jpeg_size(p+depth_bytes+4,jpeg_bytes,*profile_.color)) {
      ++rejected_payloads_;return;
    }
    frame.color=CameraColorFrame{*profile_.color,{p+depth_bytes+4,p+depth_bytes+4+jpeg_bytes}};
  } else if (size!=depth_bytes) {++rejected_payloads_;return;}
  frame.depth.width=profile_.depth.width;frame.depth.height=profile_.depth.height;
  frame.depth.depth_mm.resize(pixels);
  for (size_t i=0;i<pixels;++i) {
    const uint16_t mm=uint16_t(p[2*i])|uint16_t(p[2*i+1])<<8;
    frame.depth.depth_mm[i]=mm<=10?0:mm;
  }
  frame.depth.frame_id=next_frame_id_++;frame.depth.capture_time_ns=now_ns();
  frame.calibration=calibration_;
  if (calibration_) frame.depth.intrinsics_id=calibration_->depth.id;
  last_frame_ns_=frame.depth.capture_time_ns;
  latest_=std::make_shared<const FrameBundle>(std::move(frame));
}

void Cs30CaptureSession::on_packets(uint64_t token,const uint8_t* p,size_t n,const IsoPacketDesc* d,size_t count) {
  std::lock_guard<std::mutex> delivery(delivery_mutex_);
  std::shared_ptr<const FrameBundle> frame;
  {
    std::lock_guard<std::mutex> lock(mutex_);
    if (token!=session_ || !accepting_ || !assembler_) return;
    const auto previous=latest_;++transfers_;
    assembler_->push_transfer(p,n,d,count);
    if (latest_!=previous) frame=latest_;
  }
  if (frame && frame->calibration && frame_sink_) frame_sink_(*frame);
}

void Cs30CaptureSession::on_event(uint64_t token,const CameraStatus& status) {
  std::lock_guard<std::mutex> delivery(delivery_mutex_);
  SensorAdapter::EventCallback callback;
  {
    std::lock_guard<std::mutex> lock(mutex_);
    if (token!=session_ || !opened_ || notified_) return;
    terminal_=status;accepting_=false;latest_.reset();calibration_.reset();
    notified_=true;callback=callback_;
  }
  if (reset_sink_) reset_sink_();
  if (callback) callback(status);
}

CameraStatus Cs30CaptureSession::get_calibration(std::shared_ptr<const CameraCalibration>& calibration) {
  std::lock_guard<std::mutex> lock(mutex_);
  if (!opened_) return fail(CameraCode::kInvalidState,"设备尚未打开");
  if (!terminal_) return terminal_;
  if (!active_) return fail(CameraCode::kInvalidState,"尚未启动取流");
  if (!calibration_) return fail(CameraCode::kCalibrationUnavailable,"当前流的完整标定尚未就绪");
  calibration=calibration_;return {};
}
CameraStatus Cs30CaptureSession::get_capture_settings(CameraCaptureSettings& settings) {
  std::lock_guard<std::mutex> lock(mutex_);
  if (!opened_) return fail(CameraCode::kInvalidState,"设备尚未打开");
  if (!terminal_) return terminal_;
  // Integration conversion depends on firmware; do not label raw 0xa300 values
  // as microseconds. Unknown optional properties intentionally remain empty.
  settings=settings_;return {};
}
CameraStatus Cs30CaptureSession::get_latest_frame(uint64_t after,FrameBundle& frame) {
  std::shared_ptr<const FrameBundle> snapshot;
  {
    std::lock_guard<std::mutex> lock(mutex_);
    if (!opened_) return fail(CameraCode::kInvalidState,"设备尚未打开");
    if (!terminal_) return terminal_;
    if (!active_) return fail(CameraCode::kInvalidState,"相机已停止取流");
    snapshot=latest_;
    if (!snapshot || snapshot->depth.frame_id<=after) return fail(CameraCode::kNoNewFrame,"暂无新帧");
    if (!snapshot->calibration) return fail(CameraCode::kCalibrationUnavailable,"有图像但当前流标定不完整");
  }
  frame=*snapshot;return {};
}
void Cs30CaptureSession::stop_monitor() {
  {std::lock_guard<std::mutex> lock(mutex_);monitoring_=false;monitor_cv_.notify_all();}
  if (monitor_.joinable()) monitor_.join();
}
CameraStatus Cs30CaptureSession::stop_streaming() {
  stop_monitor();
  bool was_open=false;
  {std::lock_guard<std::mutex> lock(mutex_);was_open=opened_;accepting_=false;++session_;}
  CameraStatus status=transport_->stop_iso();
  if (was_open) {
    const auto alt=transport_->set_alt(cs30::kStreamingInterface,0);
    if (status && !alt && alt.code!=CameraCode::kDisconnected) status=alt;
  }
  std::lock_guard<std::mutex> delivery(delivery_mutex_);
  {std::lock_guard<std::mutex> lock(mutex_);clear_stream_locked();
    if(terminal_.code!=CameraCode::kDisconnected)terminal_={};}
  if (reset_sink_) reset_sink_();
  return status;
}
CameraStatus Cs30CaptureSession::close_device() {
  {std::lock_guard<std::mutex> lock(mutex_);callback_={};}
  CameraStatus status=stop_streaming();
  const auto closed=transport_->close();
  {
    std::lock_guard<std::mutex> lock(mutex_);
    opened_=false;device_id_.clear();terminal_={};notified_=false;
  }
  return status?closed:status;
}
bool Cs30CaptureSession::receiving() const {
  std::lock_guard<std::mutex> lock(mutex_);
  return active_ && terminal_ && latest_ && latest_->calibration;
}
std::string Cs30CaptureSession::diagnostics() const {
  std::lock_guard<std::mutex> lock(mutex_);
  std::ostringstream out;
  out<<"设备 "<<device_id_<<"；会话 "<<session_<<"；USB批次 "<<transfers_<<"；坏载荷 "<<rejected_payloads_;
  if (assembler_) out<<"；完整载荷 "<<assembler_->stats().frames<<"；不完整 "<<assembler_->stats().incomplete;
  if (assembler_) out<<"；包错误 "<<assembler_->stats().packet_errors<<"；UVC 错误 "<<assembler_->stats().uvc_errors;
  out<<"；固件 "<<cs30::printable(collector_.info().firmware);
  if(calibration_)out<<"；深度标定 "<<calibration_->depth.id;
  if(calibration_ && calibration_->color)out<<"；彩色 "<<calibration_->color->intrinsics.width<<"×"<<calibration_->color->intrinsics.height;
  if (!terminal_) out<<"；"<<terminal_.message;
  return out.str();
}
}  // namespace lingtouch
