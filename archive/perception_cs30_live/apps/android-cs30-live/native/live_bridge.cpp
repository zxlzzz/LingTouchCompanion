#include <jni.h>
#include <memory>
#include <mutex>
#include <string>
#include <vector>
#include "lingtouch/config.h"
#include "lingtouch/engine.h"
#include "lingtouch/depth_evidence.h"
#include "lingtouch/report_json.h"
#include "lingtouch/perception/cs30_libusb_source.h"
#include "lingtouch/transport_owner.h"
#ifdef CS30_SIMULATION
#include "fake_usb.h"
#include "test_usb_controls.h"
#define JNI_NAME(name) Java_com_lingtouch_cs30live_NativeSimulator_##name
#else
#define JNI_NAME(name) Java_com_lingtouch_cs30live_NativeCamera_##name
#endif
using namespace lingtouch;
namespace {
struct State {
  std::unique_ptr<Engine> engine;
  std::unique_ptr<Cs30LibusbSource> camera;
  std::mutex log_mutex;
  std::vector<std::string> usb_log;
  void log(const std::string& text){std::lock_guard<std::mutex> lock(log_mutex);if(usb_log.size()>=50)usb_log.erase(usb_log.begin());usb_log.push_back(text);}
  std::string logs(){std::lock_guard<std::mutex> lock(log_mutex);std::string out;for(const auto& line:usb_log)out+=line+"\n";return out;}
};
State* state(jlong h) {return reinterpret_cast<State*>(h);}
jstring str(JNIEnv* env,const std::string& s){return env->NewStringUTF(s.c_str());}
}
extern "C" {
JNIEXPORT jlong JNICALL JNI_NAME(create)(JNIEnv*,jclass) {
  auto config=default_config();if(!config)return 0;
  auto s=std::make_unique<State>();s->engine=std::make_unique<Engine>(config.value(), true);
  return reinterpret_cast<jlong>(s.release());
}
JNIEXPORT jstring JNICALL JNI_NAME(open)(JNIEnv* env,jclass,jlong h,jint fd) {
  auto* s=state(h);if(!s)return str(env,"Native core is not initialized");
  if(pending_usb_cleanups().load())return str(env,"正在回收上一次 USB 传输，请稍后重试或拔插相机");
  const auto prior=close_usb_camera(s);if(!prior)return str(env,prior.message);
  auto camera=Cs30LibusbSource::open_fd(fd,s->engine.get(),[s](const std::string& text){s->log(text);});
  if(!camera)return str(env,camera.error());
  s->camera=std::move(camera.value());
  const auto started=s->camera->start();
  if(!started)return str(env,started.message);
  return nullptr;
}
JNIEXPORT jstring JNICALL JNI_NAME(disconnect)(JNIEnv* env,jclass,jlong h) {
  if(auto* s=state(h)){const auto stopped=close_usb_camera(s);if(!stopped)return str(env,stopped.message);}
  return nullptr;
}
JNIEXPORT void JNICALL JNI_NAME(destroy)(JNIEnv*,jclass,jlong h) {
  auto* s=state(h);if(s)destroy_usb_state(s);
}
JNIEXPORT jstring JNICALL JNI_NAME(acquire)(JNIEnv* env,jclass,jlong h,jint mode) {
  auto* s=state(h);if(!s)return str(env,"Native core is not initialized");
  if(mode!=0&&(!s->camera||!s->camera->streaming()))return str(env,"相机未开流，请重新连接");
  const auto status=s->engine->set_acquisition(mode);
  return status?nullptr:str(env,status.message);
}
JNIEXPORT jstring JNICALL JNI_NAME(poll)(JNIEnv* env,jclass,jlong h) {
  auto* s=state(h);if(!s)return str(env,"{}");
  const bool connected=s->camera&&s->camera->streaming();
  auto json=depth_sim::evidence_json(s->engine->latest_grid(),connected);json.pop_back();
  json+=",\"stats\":"+stats_json(s->engine->stats());
  json+=",\"usb_callback_age_ms\":"+std::to_string(s->camera?s->camera->last_transfer_age_ms():-1.0);
  json+=",\"usb_last_transfer_status\":"+std::to_string(s->camera?s->camera->last_transfer_status():-1);
  json+=",\"usb_error_count\":"+std::to_string(s->camera?s->camera->transfer_errors():0);
  json+=",\"device\":\""+json_escape(s->engine->device_summary())+"\"}";
  json.pop_back();json+=",\"usb_log\":\""+json_escape(s->logs())+"\"}";
  return str(env,json);
}
JNIEXPORT jstring JNICALL JNI_NAME(interfaceInfo)(JNIEnv* env,jclass,jint fd,jint id) {
  return str(env,Cs30LibusbSource::interface_info(fd,id));
}
JNIEXPORT jstring JNICALL JNI_NAME(cleanupStatus)(JNIEnv* env,jclass) {
  return pending_usb_cleanups().load()?str(env,"USB 后台清理尚未完成，请稍后重试或拔插相机"):nullptr;
}
#ifdef CS30_SIMULATION
JNIEXPORT void JNICALL JNI_NAME(configure)(JNIEnv* env,jclass,jbyteArray blob) {
  std::vector<uint8_t> bytes(env->GetArrayLength(blob));
  env->GetByteArrayRegion(blob,0,static_cast<jsize>(bytes.size()),reinterpret_cast<jbyte*>(bytes.data()));
  mock_usb::configure(std::move(bytes),"");
}
JNIEXPORT void JNICALL JNI_NAME(feed)(JNIEnv* env,jclass,jbyteArray raw,jint fid) {
  if(env->GetArrayLength(raw)!=614400)return;
  std::vector<uint8_t> bytes(614400);
  env->GetByteArrayRegion(raw,0,614400,reinterpret_cast<jbyte*>(bytes.data()));
  mock_usb::enqueue(bytes,fid&1);
}
JNIEXPORT void JNICALL JNI_NAME(unplug)(JNIEnv*,jclass) {mock_usb::disconnect();}
JNIEXPORT jboolean JNICALL JNI_NAME(forceClaim)(JNIEnv*,jclass,jint id,jboolean force){return mock_java_claim(id,force);}
JNIEXPORT jboolean JNICALL JNI_NAME(javaRelease)(JNIEnv*,jclass,jint id){return mock_java_release(id);}
JNIEXPORT jstring JNICALL JNI_NAME(policyReport)(JNIEnv* env,jclass){return str(env,mock_policy_report());}
JNIEXPORT jstring JNICALL JNI_NAME(transportCheck)(JNIEnv* env,jclass,jbyteArray blob){
  std::vector<unsigned char> bytes(env->GetArrayLength(blob));env->GetByteArrayRegion(blob,0,static_cast<jsize>(bytes.size()),reinterpret_cast<jbyte*>(bytes.data()));
  try{return str(env,run_transport_regressions(bytes.data(),bytes.size()));}
  catch(const std::exception& error){env->ThrowNew(env->FindClass("java/lang/IllegalStateException"),error.what());return nullptr;}
}
#endif
}
