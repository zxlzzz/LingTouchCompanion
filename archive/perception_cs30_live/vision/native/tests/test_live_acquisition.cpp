#include <algorithm>
#include <chrono>
#include <cstring>
#include <thread>
#include "lingtouch/config.h"
#include "lingtouch/engine.h"
#include "lingtouch/perception/cs30_calibration.h"
#include "synthetic_scene.h"
#include "test_files.h"
#include "test_harness.h"
using namespace lingtouch;
namespace {
void feed(Engine& engine,const DepthFrame& frame,int fid){
  std::vector<uint8_t> raw(frame.depth_mm.size()*2);
  for(size_t i=0;i<frame.depth_mm.size();++i){raw[2*i]=static_cast<uint8_t>(frame.depth_mm[i]);raw[2*i+1]=static_cast<uint8_t>(frame.depth_mm[i]>>8);}
  std::vector<uint8_t> transfer(32*3072);std::vector<IsoPacketDesc> desc(32);size_t offset=0;
  while(offset<raw.size()){
    std::fill(transfer.begin(),transfer.end(),0);
    for(int slot=0;slot<32;++slot){desc[slot]={3072,0,0};if(offset==raw.size())continue;
      const auto n=std::min<size_t>(3070,raw.size()-offset);auto* p=transfer.data()+slot*3072;
      p[0]=2;p[1]=static_cast<uint8_t>(fid|(offset+n==raw.size()?2:0));std::memcpy(p+2,raw.data()+offset,n);
      desc[slot].actual_length=static_cast<uint32_t>(n+2);offset+=n;
    }
    engine.push_iso_transfer(transfer.data(),transfer.size(),desc.data(),desc.size());
  }
}
bool wait_processed(const Engine& e,uint64_t minimum){
  for(int i=0;i<300;++i){if(e.stats().frames_processed>=minimum)return true;std::this_thread::sleep_for(std::chrono::milliseconds(5));}
  return false;
}
}
LT_TEST(managed_and_legacy_acquisition_contracts){
  const auto blob=lt_files::read("cs30/calibration_0.bin");
  const auto cal=cs30::decode_calibration(blob.data(),blob.size());LT_CHECK(cal);if(!cal)return;
  const auto config=default_config().value();
  const auto model=DepthCameraModel::create(cal.value().depth,config.depth.undistort).value();
  lt_synth::Scene scene;scene.boxes.push_back({-0.15,0.15,1.85,2.15,0,0.5});
  const auto frame=lt_synth::render(scene,model,{1.5,30,0},DepthMeaning::kOpticalAxisZ);
  {
    Engine legacy(config);LT_CHECK(legacy.set_intrinsics(cal.value().depth));
    feed(legacy,frame,0);LT_CHECK(wait_processed(legacy,1));
    feed(legacy,frame,1);LT_CHECK(wait_processed(legacy,2));
    legacy.reset_stream();LT_CHECK(legacy.set_intrinsics(cal.value().depth));
    feed(legacy,frame,0);LT_CHECK(wait_processed(legacy,3));
  }
  {
    Engine managed(config,true);LT_CHECK(managed.set_intrinsics(cal.value().depth));
    feed(managed,frame,0);std::this_thread::sleep_for(std::chrono::milliseconds(80));
    LT_CHECK(managed.stats().frames_processed==0);
    LT_CHECK(managed.set_acquisition(1));feed(managed,frame,1);LT_CHECK(wait_processed(managed,1));
    const auto first=managed.latest_grid();LT_CHECK(first.ground.ok);
    feed(managed,frame,0);std::this_thread::sleep_for(std::chrono::milliseconds(80));
    LT_CHECK(managed.stats().frames_processed==1);
    LT_CHECK(managed.set_acquisition(2));
    const auto until=std::chrono::steady_clock::now()+std::chrono::milliseconds(1650);int fid=1;
    while(std::chrono::steady_clock::now()<until){feed(managed,frame,fid);fid=1-fid;std::this_thread::sleep_for(std::chrono::milliseconds(55));}
    LT_CHECK(managed.set_acquisition(0));const auto stopped=managed.stats().frames_processed;
    LT_CHECK(stopped>=4&&stopped<=5);
    const auto frozen=managed.latest_grid().source_frame_id;
    feed(managed,frame,fid);std::this_thread::sleep_for(std::chrono::milliseconds(100));
    LT_CHECK(managed.stats().frames_processed==stopped&&managed.latest_grid().source_frame_id==frozen);
    managed.reset_stream();LT_CHECK(managed.set_intrinsics(cal.value().depth));feed(managed,frame,0);
    std::this_thread::sleep_for(std::chrono::milliseconds(80));LT_CHECK(managed.stats().frames_processed==stopped);
  }
}
LT_TEST_MAIN()
