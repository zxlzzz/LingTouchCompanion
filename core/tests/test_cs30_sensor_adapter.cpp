// Exercise both concrete adapters against deterministic USB replies. Synthetic
// JPEG markers test framing/dimensions only; this is not a camera capture fixture.
#include "../../apps/android/app/src/main/cpp/cs30_sensor_adapter.h"
#include "../../apps/harmony/entry/src/main/cpp/cs30_sensor_adapter.h"
#include "../../apps/harmony/entry/src/main/cpp/harmony_usb_transport.h"
#include "test_harness.h"
#include <algorithm>
#include <atomic>
#include <chrono>
#include <fstream>
#include <future>
#include <iterator>

using namespace lingtouch;
namespace {
std::vector<uint8_t> read_blob(int which) {
  std::ifstream in(std::string(LINGTOUCH_SOURCE_ROOT)+"/perception/cs30/calibration_"+std::to_string(which)+".bin",std::ios::binary);
  return {std::istreambuf_iterator<char>(in),std::istreambuf_iterator<char>()};
}
struct FakeUsb final : CameraUsbTransport {
  bool present=true,authorized=true,opened=false,bad_calibration=false,fail_start=false;
  size_t slice[2]={0,0};
  std::vector<uint8_t> format,probe,commit;
  PacketSink packets,old_packets;
  EventSink events,old_events;
  CameraStatus enumerate(std::vector<CameraUsbDevice>& out) override {
    out=present?std::vector<CameraUsbDevice>{{"test-cs30",authorized}}:std::vector<CameraUsbDevice>{};return {};
  }
  CameraStatus open(const std::string&) override {
    if(!authorized)return {CameraCode::kPermissionDenied,"test denied"};
    opened=true;return {};
  }
  CameraStatus claim(int) override{return {};}
  CameraStatus set_alt(int id,int alt) override {if(id==0 && alt==0)slice[0]=slice[1]=0;return {};}
  CameraStatus control(const CameraUsbControl& c,std::vector<uint8_t>& out) override {
    if(c.request_type&0x80) {
      out.assign(c.length,0);
      if(c.value==0xc100 || c.value==0xc200) {
        const int which=c.value==0xc100?0:1;auto blob=read_blob(which);
        const size_t start=slice[which],n=std::min(size_t(55),blob.size()-start),end=start+n;
        out[0]=uint8_t(blob.size());out[1]=uint8_t(blob.size()>>8);
        out[2]=uint8_t(end);out[3]=uint8_t(end>>8);out[4]=uint8_t(n);
        if(!bad_calibration)std::copy(blob.begin()+start,blob.begin()+end,out.begin()+5);
        slice[which]=end;
      } else if(c.value==0x0100) {
        // CS30 vendor mode may exceed the UVC envelope's 640x480 frame size.
        out[18]=0;out[19]=0x60;out[20]=9;out[21]=0;out[25]=0x5a;probe=out;
      }
    } else {
      if(c.value==0xa100)format=c.data;
      if(c.value==0x0200)commit=c.data;
      out.clear();
    }
    return {};
  }
  CameraStatus start_iso(const CameraIsoConfig&,PacketSink p,EventSink e) override {
    packets=std::move(p);events=std::move(e);
    return fail_start?CameraStatus{CameraCode::kIoError,"test submit failure"}:CameraStatus{};
  }
  CameraStatus stop_iso() override {
    if(packets)old_packets=packets;if(events)old_events=events;packets={};events={};return {};
  }
  CameraStatus close() override {stop_iso();opened=false;return {};}
  void emit(const std::vector<uint8_t>& bytes,int fid=0,bool damaged=false,PacketSink sink={}) {
    if(!sink)sink=packets;
    if(!sink)return;
    size_t offset=0;
    while(offset<bytes.size()) {
      const size_t n=std::min(size_t(3070),bytes.size()-offset);
      std::vector<uint8_t> packet(n+2);packet[0]=2;
      packet[1]=uint8_t(fid|(offset+n==bytes.size()?2:0)|(damaged && offset==0?0x40:0));
      std::copy(bytes.begin()+offset,bytes.begin()+offset+n,packet.begin()+2);
      IsoPacketDesc d{uint32_t(packet.size()),uint32_t(packet.size()),0};
      sink(packet.data(),packet.size(),&d,1);offset+=n;
    }
  }
};
std::vector<uint8_t> payload(bool rgb,int width=960,int height=540) {
  std::vector<uint8_t> out(640*480*2);
  for(size_t i=0;i<out.size();i+=2){out[i]=0xe8;out[i+1]=3;}
  out[0]=5;out[1]=0;
  if(rgb) {
    // SOF with dimensions plus SOI/EOI; not a decodable JPEG image.
    std::vector<uint8_t> jpeg={0xff,0xd8,0xff,0xc0,0,11,8,uint8_t(height>>8),uint8_t(height),
      uint8_t(width>>8),uint8_t(width),1,1,0x11,0,0xff,0xd9};
    out.push_back(uint8_t(jpeg.size()));out.insert(out.end(),3,0);out.insert(out.end(),jpeg.begin(),jpeg.end());
  }
  return out;
}
template<class Adapter> void adapter_contract() {
  auto transport=std::make_unique<FakeUsb>();auto* usb=transport.get();
  int callbacks=0,frames=0,resets=0;
  Adapter camera(std::move(transport),[&](const FrameBundle&){++frames;},[&]{++resets;});
  std::vector<CameraStreamProfile> profiles(1);
  LT_CHECK(camera.get_stream_profiles(profiles).code==CameraCode::kInvalidState && profiles.size()==1);
  std::vector<std::string> ids;
  usb->present=false;LT_CHECK(camera.find_devices(ids) && ids.empty());
  LT_CHECK(camera.open_device("test-cs30").code==CameraCode::kDeviceNotFound);
  usb->present=true;LT_CHECK(camera.find_devices(ids) && ids.size()==1);
  usb->authorized=false;LT_CHECK(camera.open_device(ids[0]).code==CameraCode::kPermissionDenied);
  usb->authorized=true;LT_CHECK(camera.open_device(ids[0],[&](const CameraStatus&){++callbacks;}));
  LT_CHECK(camera.get_stream_profiles(profiles) && profiles.size()==6);
  const CameraStreamProfile rgb{CameraStreamMode::kDepthRgb,{640,480},CameraResolution{960,540}};
  auto unsupported=rgb;unsupported.color=CameraResolution{1,1};
  LT_CHECK(camera.start_streaming(unsupported).code==CameraCode::kUnsupportedProfile);
  usb->fail_start=true;LT_CHECK(!camera.start_streaming(rgb));LT_CHECK(!usb->packets);
  usb->fail_start=false;LT_CHECK(camera.start_streaming(rgb));
  LT_CHECK(usb->format.size()==25 && usb->format[9]==2 && usb->format[19]==3 && usb->format[15]==0xc0);
  LT_CHECK(usb->commit==usb->probe && usb->commit[25]==0x5a);
  std::shared_ptr<const CameraCalibration> cal;
  LT_CHECK(camera.get_calibration(cal) && cal && cal->color && cal->color->intrinsics.width==960);
  LT_CHECK(cal && cal->depth.inferred && cal->color->intrinsics.inferred);
  CameraCaptureSettings settings;settings.configured_fps=123;
  LT_CHECK(camera.get_capture_settings(settings) && !settings.configured_fps && !settings.depth_integration_us);
  FrameBundle frame;frame.depth.frame_id=999;
  LT_CHECK(camera.get_latest_frame(0,frame).code==CameraCode::kNoNewFrame && frame.depth.frame_id==999);
  usb->emit(payload(true,1920,1080));
  usb->emit(payload(true),1,true);
  LT_CHECK(camera.get_latest_frame(0,frame).code==CameraCode::kNoNewFrame && frames==0);
  usb->emit(payload(true));
  LT_CHECK(camera.get_latest_frame(0,frame));
  LT_CHECK(frame.color && frame.color->resolution.width==960 && frame.depth.depth_mm[0]==0 && frame.depth.depth_mm[1]==1000);
  LT_CHECK(frame.calibration==cal && frame.depth.capture_time_ns>0 && frames==1);
  const auto first=frame.depth.frame_id;
  LT_CHECK(camera.get_latest_frame(first,frame).code==CameraCode::kNoNewFrame);
  LT_CHECK(camera.stop_streaming());
  usb->emit(payload(true),0,false,usb->old_packets);
  LT_CHECK(camera.get_latest_frame(0,frame).code==CameraCode::kInvalidState && frames==1);
  LT_CHECK(camera.start_streaming(rgb));
  usb->emit(payload(true));LT_CHECK(camera.get_latest_frame(first,frame) && frame.depth.frame_id>first);
  auto event=usb->events;event({CameraCode::kStreamInterrupted,"test interrupted"});event({CameraCode::kStreamInterrupted,"duplicate"});
  LT_CHECK(callbacks==1 && !camera.receiving());
  LT_CHECK(camera.get_latest_frame(0,frame).code==CameraCode::kStreamInterrupted);
  LT_CHECK(camera.stop_streaming() && camera.start_streaming(rgb));
  usb->emit(payload(true));LT_CHECK(camera.receiving());
  LT_CHECK(camera.close_device());
  usb->emit(payload(true),0,false,usb->old_packets);usb->old_events({CameraCode::kDisconnected,"late"});
  LT_CHECK(callbacks==1 && frames==3 && resets>0 && !usb->opened);
  LT_CHECK(camera.find_devices(ids) && camera.open_device(ids[0]));
  usb->bad_calibration=true;LT_CHECK(camera.start_streaming({CameraStreamMode::kDepth,{640,480},std::nullopt}));
  usb->emit(payload(false));
  auto saved=cal;
  LT_CHECK(camera.get_calibration(cal).code==CameraCode::kCalibrationUnavailable && cal==saved);
  LT_CHECK(camera.get_latest_frame(0,frame).code==CameraCode::kCalibrationUnavailable);
}
}
LT_TEST(android_sensor_contract){adapter_contract<AndroidCs30SensorAdapter>();}
LT_TEST(harmony_sensor_contract){adapter_contract<HarmonyCs30SensorAdapter>();}

LT_TEST(first_frame_timeout_reports_once_and_can_restart) {
  auto usb=std::make_unique<FakeUsb>();
  AndroidCs30SensorAdapter camera(std::move(usb));
  std::vector<std::string> ids;std::promise<CameraStatus> signal;auto event=signal.get_future();
  LT_CHECK(camera.find_devices(ids));
  LT_CHECK(camera.open_device(ids[0],[&](const CameraStatus& s){signal.set_value(s);}));
  const CameraStreamProfile depth{CameraStreamMode::kDepth,{640,480},std::nullopt};
  LT_CHECK(camera.start_streaming(depth));
  const bool notified=event.wait_for(std::chrono::seconds(7))==std::future_status::ready;
  LT_CHECK(notified);
  if(notified)LT_CHECK(event.get().code==CameraCode::kStreamInterrupted);
  LT_CHECK(!camera.receiving());
  LT_CHECK(camera.stop_streaming() && camera.start_streaming(depth));
}

LT_TEST(harmony_bridge_async_completion_epochs_and_abort) {
  HarmonyUsbBridge bridge;uint64_t previous=0;
  bridge.set_dispatcher([&](const HarmonyUsbCommand& c) {
    if(previous)bridge.complete(previous,{CameraCode::kIoError,"late"},{});
    previous=c.request_id;HarmonyUsbReply out;out.devices.push_back({"one",true});
    bridge.complete(c.request_id,{},std::move(out));return true;
  });
  HarmonyUsbReply reply;
  LT_CHECK(bridge.execute({},reply) && reply.devices.size()==1);
  LT_CHECK(bridge.execute({},reply) && reply.devices.size()==1);
  std::atomic<int> packets{0},events{0};
  std::promise<void> got_packet,got_event;
  auto packet_ready=got_packet.get_future(),event_ready=got_event.get_future();
  bridge.set_sinks(2,[&](const uint8_t*,size_t,const IsoPacketDesc*,size_t){++packets;got_packet.set_value();},
      [&](const CameraStatus&){++events;got_event.set_value();});
  bridge.push_packets(1,nullptr,0,nullptr,0);bridge.push_event(1,{});
  bridge.push_packets(2,nullptr,0,nullptr,0);
  LT_CHECK(packet_ready.wait_for(std::chrono::seconds(2))==std::future_status::ready);
  bridge.push_event(2,{});
  LT_CHECK(event_ready.wait_for(std::chrono::seconds(2))==std::future_status::ready);
  LT_CHECK(packets==1 && events==1);
  std::promise<void> dispatched;auto ready=dispatched.get_future();
  bridge.set_dispatcher([&](const HarmonyUsbCommand&){dispatched.set_value();return true;});
  auto work=std::async(std::launch::async,[&]{HarmonyUsbReply r;return bridge.execute({},r);});
  LT_CHECK(ready.wait_for(std::chrono::seconds(2))==std::future_status::ready);
  bridge.abort();
  LT_CHECK(work.wait_for(std::chrono::seconds(2))==std::future_status::ready);
  LT_CHECK(work.get().code==CameraCode::kDisconnected);
  bridge.push_packets(2,nullptr,0,nullptr,0);LT_CHECK(packets==1);
}

LT_TEST(harmony_receive_queue_copies_buffers_and_bounds_backlog) {
  HarmonyUsbBridge bridge;
  std::promise<void> entered,release,failed;
  auto entered_ready=entered.get_future();
  auto release_ready=release.get_future().share();
  auto failed_ready=failed.get_future();
  std::atomic<int> value{-1};
  bridge.set_sinks(10,[&](const uint8_t* p,size_t,const IsoPacketDesc*,size_t){
    value=p[0];entered.set_value();release_ready.wait();
  },[&](const CameraStatus&){failed.set_value();},16);
  uint8_t bytes[16]={42};IsoPacketDesc desc{16,16,0};
  bridge.push_packets(10,bytes,sizeof(bytes),&desc,1);
  bytes[0]=99; // The platform is free to refill the same buffer immediately.
  LT_CHECK(entered_ready.wait_for(std::chrono::seconds(2))==std::future_status::ready);
  LT_CHECK(value==42);
  // A blocked consumer must not block the producer or retain an unbounded list.
  for(int i=0;i<40;++i)bridge.push_packets(10,bytes,sizeof(bytes),&desc,1);
  const auto diagnostics=bridge.receive_diagnostics();
  LT_CHECK(diagnostics.find("溢出 1")!=std::string::npos);
  release.set_value();
  LT_CHECK(failed_ready.wait_for(std::chrono::seconds(2))==std::future_status::ready);
  bridge.set_sinks(11,{},{});
}
LT_TEST_MAIN()
