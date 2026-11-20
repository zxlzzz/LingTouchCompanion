#include "lingtouch/engine.h"
#include "lingtouch/config.h"
#include "lingtouch/report_json.h"
#include "lingtouch/depth_evidence.h"
#include "lingtouch/perception/cs30_libusb_source.h"
#include <libusb.h>
#include <chrono>
#include <fstream>
#include <iostream>
#include <sstream>
#include <thread>
#include <stdexcept>
#include <iomanip>
using namespace lingtouch;
namespace {
void save(const std::string& path,const std::string& text){std::ofstream f(path,std::ios::binary);f<<text;if(!f)throw std::runtime_error("Cannot write output");}
OccupancyGrid await(Engine& e,uint64_t after){
  const auto end=std::chrono::steady_clock::now()+std::chrono::seconds(8);
  while(std::chrono::steady_clock::now()<end){auto g=e.latest_grid();if(g.status!=GridStatus::kNoFrame&&g.source_frame_id>after)return g;std::this_thread::sleep_for(std::chrono::milliseconds(10));}
  throw std::runtime_error("No newly processed hardware frame within 8 seconds");
}
void require(bool b,const char* text){if(!b)throw std::runtime_error(text);}
}
int main(int argc,char** argv){
  if(argc!=2)return 2;const std::string prefix=argv[1];std::ofstream logs(prefix+".log",std::ios::binary);
  try{
    libusb_context* enumeration=nullptr;require(libusb_init_context(&enumeration,nullptr,0)==0,"USB enumeration init failed");
    libusb_device** devices=nullptr;const auto count=libusb_get_device_list(enumeration,&devices);
    require(count>=0,"USB list failed");int found=0;std::string inventory="[";
    for(ssize_t i=0;i<count;++i){libusb_device_descriptor d{};if(libusb_get_device_descriptor(devices[i],&d))continue;
      if(d.idVendor!=0x2207||d.idProduct!=0x0016)continue;
      if(found++)inventory+=",";inventory+="{\"bus\":"+std::to_string(libusb_get_bus_number(devices[i]))+",\"address\":"+std::to_string(libusb_get_device_address(devices[i]))+",\"speed\":"+std::to_string(libusb_get_device_speed(devices[i]))+"}";
    }
    libusb_free_device_list(devices,1);libusb_exit(enumeration);inventory+="]";
    require(found>0,"Physical CS30 not found");save(prefix+".inventory.json",inventory);
    Engine engine(default_config().value(), true);std::string cycles="[";
    for(int cycle=0;cycle<2;++cycle){
      std::cout<<"Opening real CS30 cycle "<<cycle<<std::endl;
      auto opened=Cs30LibusbSource::open_vid_pid(0x2207,0x0016,&engine,[&](const std::string& text){logs<<text<<"\n";logs.flush();});
      require(static_cast<bool>(opened),opened.error().c_str());auto camera=std::move(opened.value());
      const auto start=camera->start();require(static_cast<bool>(start),start.message.c_str());
      auto in=engine.intrinsics();require(in.has_value(),"Camera calibration missing");
      std::ostringstream k;k<<std::setprecision(17)<<"{\"width\":"<<in->width<<",\"height\":"<<in->height<<",\"fx\":"<<in->fx<<",\"fy\":"<<in->fy<<",\"cx\":"<<in->cx<<",\"cy\":"<<in->cy<<",\"distortion\":["<<in->k1<<","<<in->k2<<","<<in->p1<<","<<in->p2<<","<<in->k3<<"],\"id\":\""<<json_escape(in->id)<<"\"}";
      save(prefix+".intrinsics.json",k.str());
      const auto before=engine.stats().frames_processed;
      std::this_thread::sleep_for(std::chrono::milliseconds(600));require(engine.stats().frames_processed==before,"Idle unexpectedly processed frames");
      require(static_cast<bool>(engine.set_acquisition(1)),"Manual arm failed");auto one=await(engine,0);
      const auto manual_count=engine.stats().frames_processed;
      std::this_thread::sleep_for(std::chrono::milliseconds(700));require(engine.stats().frames_processed==manual_count,"Manual captured more than one frame");
      require(static_cast<bool>(engine.save_latest_frame(prefix+".cycle"+std::to_string(cycle)+".raw")),"Cannot save measured depth");
      const auto auto_before=engine.stats().frames_processed;
      require(static_cast<bool>(engine.set_acquisition(2)),"Auto arm failed");
      std::this_thread::sleep_for(std::chrono::milliseconds(3200));
      engine.set_acquisition(0);const auto last=engine.latest_grid();const auto auto_count=engine.stats().frames_processed-auto_before;
      require(auto_count>=4&&auto_count<=8,"Automatic frame count outside expected range");
      const auto frozen=engine.stats().frames_processed;
      std::this_thread::sleep_for(std::chrono::milliseconds(650));require(engine.stats().frames_processed==frozen,"Stop failed to freeze processing");
      const auto stats=engine.stats();require(stats.assembler.frames>=10,"Too few physical sensor frames");
      save(prefix+".cycle"+std::to_string(cycle)+".grid.json",depth_sim::evidence_json(last));
      auto stopped=camera->stop();require(static_cast<bool>(stopped),stopped.message.c_str());camera.reset();
      if(cycle)cycles+=",";
      cycles+="{\"cycle\":"+std::to_string(cycle)+",\"auto_processed_in_3200ms\":"+std::to_string(auto_count)+",\"clean_stop\":true,\"stats\":"+stats_json(stats)+",\"manual_ground_valid\":"+(one.ground.ok?"true":"false")+"}";
      std::cout<<"Cycle "<<cycle<<" received "<<stats.assembler.frames<<" complete physical frames; auto processed "<<auto_count<<std::endl;
    }
    cycles+="]";save(prefix+".json","{\"passed\":true,\"physical_camera\":true,\"inventory\":"+inventory+",\"cycles\":"+cycles+"}");
    return 0;
  }catch(const std::exception& e){std::cerr<<e.what()<<std::endl;save(prefix+".json","{\"passed\":false,\"error\":\""+json_escape(e.what())+"\"}");return 1;}
}
