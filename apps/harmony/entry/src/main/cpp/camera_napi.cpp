#include "camera_napi.h"
#include "cs30_sensor_adapter.h"
#include "harmony_usb_transport.h"
#include "napi_bytes.h"
#include "lingtouch/report_json.h"
#include <atomic>
#include <cmath>
#include <cstring>
#include <exception>
#include <utility>

namespace {
using namespace lingtouch;
napi_value text(napi_env e,const std::string& s){napi_value v;napi_create_string_utf8(e,s.c_str(),s.size(),&v);return v;}
napi_value number(napi_env e,double n){napi_value v;napi_create_double(e,n,&v);return v;}
napi_value object(napi_env e){napi_value v;napi_create_object(e,&v);return v;}
napi_value empty(napi_env e){napi_value v;napi_get_undefined(e,&v);return v;}
void put(napi_env e,napi_value o,const char* k,napi_value v){napi_set_named_property(e,o,k,v);}
bool string_arg(napi_env e,napi_value v,std::string& s) {
  size_t n=0;if(napi_get_value_string_utf8(e,v,nullptr,0,&n)!=napi_ok || n>4096)return false;
  std::vector<char> b(n+1);if(napi_get_value_string_utf8(e,v,b.data(),b.size(),&n)!=napi_ok)return false;
  s.assign(b.data(),n);return true;
}
bool integer(napi_env e,napi_value v,uint64_t& n) {
  double d=0;if(napi_get_value_double(e,v,&d)!=napi_ok || !std::isfinite(d) || d<0 || d>9007199254740991.0 || std::floor(d)!=d)return false;
  n=uint64_t(d);return true;
}
bool bytes(napi_env e,napi_value v,const uint8_t*& p,size_t& n) {
  return lingtouch_napi_bytes(e,v,&p,&n) && n<=8*1024*1024;
}
napi_value buffer(napi_env e,const std::vector<uint8_t>& data) {
  napi_value v;void* p=nullptr;napi_create_arraybuffer(e,data.size(),&p,&v);
  if(!data.empty())std::memcpy(p,data.data(),data.size());return v;
}
struct Api {
  std::shared_ptr<HarmonyUsbBridge> bridge=std::make_shared<HarmonyUsbBridge>();
  std::shared_ptr<HarmonyCs30SensorAdapter> camera;
  std::function<std::shared_ptr<Engine>()> get_engine;
  napi_threadsafe_function dispatcher=nullptr;
  std::mutex mutex;
  CameraStatus status{CameraCode::kOk,"未连接"};
  std::string diagnostics;
  bool receiving=false;
  std::shared_ptr<const FrameBundle> preview;
  uint64_t preview_epoch=0;
  bool preview_requested=true;
  uint64_t received_frames=0,capture_frame_id=0,preview_copies=0;
  int64_t last_capture_ns=0,last_diagnostics_ns=0;
  std::atomic<bool> busy{false};
  std::atomic<bool> closing{false};
  CameraStreamProfile profile;
  void update(CameraStatus s,bool frames=false,std::string details={}){
    std::lock_guard<std::mutex> lock(mutex);status=std::move(s);receiving=frames;
    if(!frames){preview.reset();preview_requested=true;}
    if(!details.empty())diagnostics=std::move(details);
  }
  void reset_preview(){
    std::lock_guard<std::mutex> lock(mutex);preview.reset();receiving=false;++preview_epoch;
    preview_requested=true;received_frames=0;capture_frame_id=0;preview_copies=0;
    last_capture_ns=0;last_diagnostics_ns=0;
  }
};
using Handle=std::shared_ptr<Api>;
Handle api_arg(napi_env e,napi_callback_info i,size_t& n,napi_value* values) {
  void* data=nullptr;napi_get_cb_info(e,i,&n,values,nullptr,&data);
  return *static_cast<Handle*>(data);
}
napi_value result(napi_env e,const CameraStatus& status) {
  auto o=object(e);put(e,o,"code",number(e,int(status.code)));put(e,o,"message",text(e,status.message));return o;
}
void dispatch_js(napi_env e,napi_value callback,void*,void* data) {
  std::unique_ptr<HarmonyUsbCommand> request(static_cast<HarmonyUsbCommand*>(data));
  if(!e || !callback)return;
  auto o=object(e);const auto& c=*request;
  put(e,o,"requestId",number(e,double(c.request_id)));put(e,o,"epoch",number(e,double(c.epoch)));
  put(e,o,"operation",number(e,int(c.operation)));put(e,o,"deviceId",text(e,c.device_id));
  put(e,o,"interfaceNumber",number(e,c.interface_number));put(e,o,"alternate",number(e,c.alternate));
  put(e,o,"requestType",number(e,c.control.request_type));put(e,o,"request",number(e,c.control.request));
  put(e,o,"value",number(e,c.control.value));put(e,o,"index",number(e,c.control.index));
  put(e,o,"length",number(e,c.control.length));put(e,o,"timeoutMs",number(e,c.control.timeout_ms));
  put(e,o,"data",buffer(e,c.control.data));put(e,o,"endpoint",number(e,c.iso.endpoint));
  put(e,o,"transfers",number(e,c.iso.transfers));put(e,o,"packets",number(e,c.iso.packets));
  put(e,o,"packetBytes",number(e,c.iso.packet_bytes));put(e,o,"isoTimeoutMs",number(e,c.iso.timeout_ms));
  napi_value ignored;napi_call_function(e,empty(e),callback,1,&o,&ignored);
}
napi_value set_handler(napi_env e,napi_callback_info i) {
  size_t n=1;napi_value args[1];auto api=api_arg(e,i,n,args);
  napi_valuetype type;if(n<1 || napi_typeof(e,args[0],&type)!=napi_ok || type!=napi_function){napi_throw_type_error(e,nullptr,"需要 USB 系统处理函数");return nullptr;}
  if(api->dispatcher)return empty(e);
  const auto created=napi_create_threadsafe_function(e,args[0],nullptr,text(e,"CS30 USB system operations"),8,1,
      nullptr,nullptr,nullptr,dispatch_js,&api->dispatcher);
  if(created!=napi_ok){napi_throw_error(e,nullptr,"无法创建 USB 系统桥接");return nullptr;}
  // The USB bridge must not keep the application alive after its environment exits.
  napi_unref_threadsafe_function(e,api->dispatcher);
  std::weak_ptr<Api> weak=api;
  api->bridge->set_dispatcher([weak](const HarmonyUsbCommand& command) {
    auto api=weak.lock();if(!api || api->closing)return false;
    auto request=std::make_unique<HarmonyUsbCommand>(command);
    if(napi_call_threadsafe_function(api->dispatcher,request.get(),napi_tsfn_nonblocking)!=napi_ok)return false;
    request.release();return true;
  });
  return empty(e);
}
napi_value complete_usb(napi_env e,napi_callback_info i) {
  size_t n=5;napi_value args[5];auto api=api_arg(e,i,n,args);uint64_t id=0,code=0;
  std::string message;const uint8_t* p=nullptr;size_t size=0;bool is_array=false;
  if(n<5 || !integer(e,args[0],id) || !integer(e,args[1],code) || code>int(CameraCode::kIoError) ||
      !string_arg(e,args[2],message) || !bytes(e,args[3],p,size) || size>65535 ||
      napi_is_array(e,args[4],&is_array)!=napi_ok || !is_array) {
    napi_throw_type_error(e,nullptr,"USB 完成结果参数错误");return nullptr;
  }
  HarmonyUsbReply reply;if(size)reply.data.assign(p,p+size);
  uint32_t count=0;napi_get_array_length(e,args[4],&count);
  if(count>128){napi_throw_range_error(e,nullptr,"USB 设备列表过长");return nullptr;}
  for(uint32_t k=0;k<count;++k) {
    napi_value d,v,allowed;napi_get_element(e,args[4],k,&d);
    napi_get_named_property(e,d,"id",&v);napi_get_named_property(e,d,"authorized",&allowed);
    CameraUsbDevice device;
    if(!string_arg(e,v,device.id) || napi_get_value_bool(e,allowed,&device.authorized)!=napi_ok){napi_throw_type_error(e,nullptr,"USB 设备条目错误");return nullptr;}
    reply.devices.push_back(std::move(device));
  }
  api->bridge->complete(id,{CameraCode(code),std::move(message)},std::move(reply));return empty(e);
}
napi_value push_packets(napi_env e,napi_callback_info i) {
  size_t n=3;napi_value args[3];auto api=api_arg(e,i,n,args);uint64_t epoch=0;
  const uint8_t* p=nullptr;const uint8_t* d=nullptr;size_t size=0,desc_size=0;
  if(n<3 || !integer(e,args[0],epoch) || !bytes(e,args[1],p,size) || !bytes(e,args[2],d,desc_size) ||
      size>128*3072 || desc_size%12 || desc_size>128*12){napi_throw_type_error(e,nullptr,"等时数据或包描述错误");return nullptr;}
  std::array<IsoPacketDesc,128> descs;
  const size_t desc_count=desc_size/12;
  for(size_t k=0;k<desc_count;++k) {
    int32_t v[3];std::memcpy(v,d+k*12,12);
    if(v[0]<0 || v[1]<0){
      const std::string message="等时包长度不能为负数，包 "+std::to_string(k)+
          " length="+std::to_string(v[0])+" actualLength="+std::to_string(v[1])+" status="+std::to_string(v[2]);
      napi_throw_range_error(e,nullptr,message.c_str());return nullptr;
    }
    descs[k]={uint32_t(v[0]),uint32_t(v[1]),v[2]};
  }
  api->bridge->push_packets(epoch,p,size,descs.data(),desc_count);return empty(e);
}
napi_value push_event(napi_env e,napi_callback_info i) {
  size_t n=3;napi_value args[3];auto api=api_arg(e,i,n,args);uint64_t epoch=0,code=0;std::string message;
  if(n<3 || !integer(e,args[0],epoch) || !integer(e,args[1],code) ||
      (code!=int(CameraCode::kDisconnected) && code!=int(CameraCode::kStreamInterrupted)) || !string_arg(e,args[2],message)) {
    napi_throw_type_error(e,nullptr,"相机事件参数错误");return nullptr;
  }
  api->bridge->push_event(epoch,{CameraCode(code),std::move(message)});return empty(e);
}
struct Work {
  Handle api;napi_threadsafe_function completion=nullptr;napi_deferred deferred=nullptr;
  std::string operation,id;bool color=true;CameraStatus status;
};
void execute(napi_env,void* value) {
  auto& job=*static_cast<Work*>(value);auto api=job.api;
  try {
    const auto engine=api->get_engine();
    if(!engine){job.status={CameraCode::kInvalidState,"核心尚未初始化"};api->update(job.status);return;}
    if(!api->camera) {
      std::weak_ptr<Api> weak=api;
      api->camera=std::make_shared<HarmonyCs30SensorAdapter>(std::make_unique<HarmonyUsbTransport>(api->bridge),
          [weak,engine](const FrameBundle& f){
            const auto s=engine->submit_frame(f);
            if(auto api=weak.lock()){
              bool refresh_diagnostics=false;
              {
                std::lock_guard<std::mutex> lock(api->mutex);
                refresh_diagnostics=api->last_diagnostics_ns==0 ||
                    f.depth.capture_time_ns-api->last_diagnostics_ns>=1000000000LL;
                if(refresh_diagnostics)api->last_diagnostics_ns=f.depth.capture_time_ns;
              }
              const auto details=refresh_diagnostics?api->camera->diagnostics():std::string{};
              std::lock_guard<std::mutex> lock(api->mutex);
              if(s){
                ++api->received_frames;api->capture_frame_id=f.depth.frame_id;
                api->last_capture_ns=f.depth.capture_time_ns;
                // Demand driven, one retained capture group. Paused/slow UI
                // does not force a full depth+JPEG allocation for every frame.
                if(api->preview_requested){
                  api->preview=std::make_shared<const FrameBundle>(f);
                  api->preview_requested=false;++api->preview_copies;
                }
                if(!api->receiving)api->status={CameraCode::kOk,f.color?"正在接收深度和彩色":"正在接收深度"};
              } else {
                api->status={CameraCode::kStreamInterrupted,s.message};api->preview.reset();api->preview_requested=true;
              }
              api->receiving=bool(s);if(refresh_diagnostics)api->diagnostics=details;
            }
          },[weak,engine]{engine->reset_stream();if(auto api=weak.lock())api->reset_preview();});
    }
    auto& camera=*api->camera;
    if(job.operation=="connect" || job.operation=="start")api->update({CameraCode::kOk,"已发起取流，等待完整帧和标定"});
    if(job.operation=="connect") {
      job.status=camera.close_device();
      std::vector<std::string> ids;
      if(job.status)job.status=camera.find_devices(ids);
      if(job.status)job.status=camera.open_device(job.id,[weak=std::weak_ptr<Api>(api)](const CameraStatus& s){
        if(auto api=weak.lock())api->update(s,false,api->camera->diagnostics());
      });
      api->profile={job.color?CameraStreamMode::kDepthRgb:CameraStreamMode::kDepth,{640,480},std::nullopt};
      if(job.color)api->profile.color=CameraResolution{960,540};
      if(job.status)job.status=camera.start_streaming(api->profile);
    } else if(job.operation=="stop") job.status=camera.stop_streaming();
    else if(job.operation=="start") job.status=camera.start_streaming(api->profile);
    else if(job.operation=="close") job.status=camera.close_device();
    else job.status={CameraCode::kInvalidState,"未知采集操作"};
    if(!job.status && job.operation=="connect")camera.close_device();
  } catch(const std::exception& error){job.status={CameraCode::kIoError,error.what()};}
  if(!job.status)api->update(job.status);
  else if(job.operation=="close" || job.operation=="stop")api->update({CameraCode::kOk,job.operation=="close"?"未连接":"已停止取流，设备保持打开"});
  else {
    std::shared_ptr<const CameraCalibration> calibration;
    const auto status=api->camera->get_calibration(calibration);
    if(!status){std::lock_guard<std::mutex> lock(api->mutex);if(api->status.code==CameraCode::kOk)api->status=status;}
  }
}
void finished(napi_env e,napi_status status,void* value) {
  std::unique_ptr<Work> job(static_cast<Work*>(value));job->api->busy=false;
  if(status!=napi_ok)job->status={CameraCode::kIoError,"原生相机任务被取消"};
  if(!job->api->closing)napi_resolve_deferred(e,job->deferred,result(e,job->status));
}
void complete_operation(napi_env e,napi_value,void*,void* value) {
  if(e)finished(e,napi_ok,value);
  else {
    std::unique_ptr<Work> job(static_cast<Work*>(value));
    job->api->busy=false;
  }
}
napi_value operation(napi_env e,napi_callback_info i) {
  size_t n=3;napi_value args[3];auto api=api_arg(e,i,n,args);
  auto job=std::make_unique<Work>();job->api=api;
  if(n<3 || !string_arg(e,args[0],job->operation) || !string_arg(e,args[1],job->id) ||
      napi_get_value_bool(e,args[2],&job->color)!=napi_ok){napi_throw_type_error(e,nullptr,"相机操作参数错误");return nullptr;}
  napi_value promise;napi_create_promise(e,&job->deferred,&promise);
  if(api->busy.exchange(true)) {napi_resolve_deferred(e,job->deferred,result(e,{CameraCode::kInvalidState,"相机正在处理另一个操作"}));return promise;}
  // ImageKit also uses asynchronous system work. Camera stop/reconnect must
  // not queue behind stalled image jobs in the shared libuv worker pool.
  if(napi_create_threadsafe_function(e,nullptr,nullptr,text(e,"CS30 capture completion"),1,1,
      nullptr,nullptr,nullptr,complete_operation,&job->completion)!=napi_ok) {
    api->busy=false;napi_resolve_deferred(e,job->deferred,result(e,{CameraCode::kIoError,"无法创建采集任务"}));return promise;
  }
  napi_unref_threadsafe_function(e,job->completion);
  try {
    auto* raw=job.get();
    std::thread([raw] {
      auto api=raw->api;const auto completion=raw->completion;
      execute(nullptr,raw);
      if(napi_call_threadsafe_function(completion,raw,napi_tsfn_nonblocking)!=napi_ok) {
        api->busy=false;delete raw;
      }
      napi_release_threadsafe_function(completion,napi_tsfn_release);
    }).detach();
  } catch(const std::exception& error) {
    api->busy=false;napi_release_threadsafe_function(job->completion,napi_tsfn_abort);
    napi_resolve_deferred(e,job->deferred,result(e,{CameraCode::kIoError,error.what()}));return promise;
  }
  job.release();return promise;
}
napi_value camera_status(napi_env e,napi_callback_info i) {
  size_t n=0;auto api=api_arg(e,i,n,nullptr);std::lock_guard<std::mutex> lock(api->mutex);
  auto o=result(e,api->status);napi_value b;napi_get_boolean(e,api->receiving,&b);put(e,o,"receiving",b);
  put(e,o,"previewEpoch",number(e,double(api->preview_epoch)));
  put(e,o,"receivedFrames",number(e,double(api->received_frames)));
  put(e,o,"captureFrameId",number(e,double(api->capture_frame_id)));
  put(e,o,"previewCopies",number(e,double(api->preview_copies)));
  put(e,o,"lastFrameAgeMs",number(e,api->last_capture_ns?
      double(monotonic_now_ns()-api->last_capture_ns)/1000000.0:-1));
  put(e,o,"diagnostics",text(e,api->diagnostics+"；"+api->bridge->receive_diagnostics()));return o;
}
napi_value camera_preview(napi_env e,napi_callback_info i) {
  size_t n=2;napi_value args[2];auto api=api_arg(e,i,n,args);uint64_t after=0,channels=3;
  if(n<1 || !integer(e,args[0],after) || (n>1 && (!integer(e,args[1],channels) || channels<1 || channels>3))){
    napi_throw_type_error(e,nullptr,"预览需要上次显示的帧号");return nullptr;
  }
  std::shared_ptr<const FrameBundle> frame;uint64_t epoch=0;
  {
    std::lock_guard<std::mutex> lock(api->mutex);
    api->preview_requested=true;
    if(!api->receiving || !api->preview || api->preview->depth.frame_id<=after)return empty(e);
    frame=api->preview;epoch=api->preview_epoch;
  }
  const auto& depth=frame->depth;
  // 320x240 preview, fixed 0.1-5 m scale: invalid black, near bright,
  // far dark. This is visualization only; the perception input is unchanged.
  const int step=(depth.width+319)/320;
  const int w=(depth.width+step-1)/step,h=(depth.height+step-1)/step;
  std::vector<uint8_t> rgba;
  if(channels&2)rgba.resize(size_t(w)*h*4);
  if(channels&2)for(int y=0;y<h;++y)for(int x=0;x<w;++x){
    const uint32_t mm=depth.depth_mm[size_t(y*step)*depth.width+x*step];
    const uint8_t gray=mm>=100 && mm<=5000?uint8_t(255-(mm-100)*223/4900):0;
    const size_t at=(size_t(y)*w+x)*4;
    rgba[at]=rgba[at+1]=rgba[at+2]=gray;rgba[at+3]=255;
  }
  auto o=object(e);put(e,o,"epoch",number(e,double(epoch)));
  put(e,o,"frameId",number(e,double(depth.frame_id)));
  put(e,o,"depthWidth",number(e,w));put(e,o,"depthHeight",number(e,h));
  put(e,o,"depthRgba",buffer(e,rgba));
  put(e,o,"colorWidth",number(e,frame->color?frame->color->resolution.width:0));
  put(e,o,"colorHeight",number(e,frame->color?frame->color->resolution.height:0));
  if((channels&1) && frame->color)put(e,o,"colorJpeg",buffer(e,frame->color->jpeg));
  else put(e,o,"colorJpeg",buffer(e,{}));
  return o;
}
} // namespace

void register_camera_api(napi_env env,napi_value exports,std::function<std::shared_ptr<lingtouch::Engine>()> getter) {
  auto* handle=new Handle(std::make_shared<Api>());(*handle)->get_engine=std::move(getter);
  napi_property_descriptor properties[]={
    {"cameraSetUsbHandler",nullptr,set_handler,nullptr,nullptr,nullptr,napi_default,handle},
    {"cameraCompleteUsb",nullptr,complete_usb,nullptr,nullptr,nullptr,napi_default,handle},
    {"cameraPushIso",nullptr,push_packets,nullptr,nullptr,nullptr,napi_default,handle},
    {"cameraPushEvent",nullptr,push_event,nullptr,nullptr,nullptr,napi_default,handle},
    {"cameraOperation",nullptr,operation,nullptr,nullptr,nullptr,napi_default,handle},
    {"cameraStatus",nullptr,camera_status,nullptr,nullptr,nullptr,napi_default,handle},
    {"cameraPreview",nullptr,camera_preview,nullptr,nullptr,nullptr,napi_default,handle}
  };
  napi_define_properties(env,exports,sizeof(properties)/sizeof(properties[0]),properties);
  napi_add_env_cleanup_hook(env,[](void* data){
    std::unique_ptr<Handle> handle(static_cast<Handle*>(data));auto api=*handle;
    api->closing=true;api->bridge->abort();
    if(api->dispatcher)napi_release_threadsafe_function(api->dispatcher,napi_tsfn_abort);
  },handle);
}
