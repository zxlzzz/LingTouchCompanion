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
#ifdef CS30_SIMULATION
#include <cmath>
#include "lingtouch/perception/pipeline.h"
#endif
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
#ifdef CS30_SIMULATION
  constexpr bool review=false; // Keep the established 1.7 fixture regression.
#else
  constexpr bool review=true;
#endif
  auto s=std::make_unique<State>();s->engine=std::make_unique<Engine>(config.value(), true, review);
  return reinterpret_cast<jlong>(s.release());
}
JNIEXPORT jstring JNICALL JNI_NAME(open)(JNIEnv* env,jclass,jlong h,jint fd,jboolean restoreStreamIdle) {
  auto* s=state(h);if(!s)return str(env,"Native core is not initialized");
  if(pending_usb_cleanups().load())return str(env,"正在回收上一次 USB 传输，请稍后重试或拔插相机");
  const auto prior=close_usb_camera(s);if(!prior)return str(env,prior.message);
  auto camera=Cs30LibusbSource::open_fd(fd,s->engine.get(),[s](const std::string& text){s->log(text);});
  if(!camera)return str(env,camera.error());
  s->camera=std::move(camera.value());
  const auto started=s->camera->start(restoreStreamIdle == JNI_TRUE);
  if(!started)return str(env,started.message);
  return nullptr;
}
JNIEXPORT jstring JNICALL JNI_NAME(disconnect)(JNIEnv* env,jclass,jlong h) {
  if(auto* s=state(h)){const auto stopped=close_usb_camera(s);if(!stopped)return str(env,stopped.message);}
  return nullptr;
}
JNIEXPORT jint JNICALL JNI_NAME(resetAfterStartupError)(JNIEnv*, jclass, jlong h) {
  auto* s = state(h);
  return s && s->camera ? static_cast<jint>(s->camera->reset_after_startup_error()) : 0;
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
JNIEXPORT jbyteArray JNICALL JNI_NAME(autoReflectionFixture)(JNIEnv* env,jclass,jlong h) {
  const auto intrinsics = state(h)->engine->intrinsics();
  const auto config = default_config();
  if (!intrinsics || !config) return nullptr;
  const auto camera = DepthCameraModel::create(*intrinsics, config.value().depth.undistort);
  if (!camera) return nullptr;
  const auto& model = camera.value();
  DepthFrame frame;
  frame.width = model.width();
  frame.height = model.height();
  frame.depth_mm.resize(static_cast<size_t>(frame.width) * frame.height);
  for (size_t i = 0; i < frame.depth_mm.size(); ++i) {
    if (!model.pixel_valid(i)) continue;
    const double x = model.x(i), y = model.y(i);
    double z = 0;
    if (y >= .28 && y <= .80 && std::abs(x) < .68) z = 1.32 / y;
    if (y >= -.50 && y <= -.30) {
      const double near = 1.05 + 1.5 * (y + .50);
      if (x * near >= .66 && x * near <= .98) z = near;
    }
    frame.depth_mm[i] = static_cast<uint16_t>(std::lround(z * 1000));
  }
  // The coherent patch must light the near-right dot when the review is bypassed.
  DepthPipeline unreviewed(config.value());
  if (!unreviewed.set_intrinsics(*intrinsics)) return nullptr;
  const auto baseline = unreviewed.process(frame);
  if (!baseline.ground.ok || baseline.evidence.obstacle[51] < 3) {
    env->ThrowNew(env->FindClass("java/lang/IllegalStateException"), "Auto reflection fixture does not light the unreviewed dot");
    return nullptr;
  }
  std::vector<jbyte> raw(frame.depth_mm.size() * 2);
  for (size_t i = 0; i < frame.depth_mm.size(); ++i) {
    raw[2*i] = static_cast<jbyte>(frame.depth_mm[i] & 0xff);
    raw[2*i+1] = static_cast<jbyte>(frame.depth_mm[i] >> 8);
  }
  auto array = env->NewByteArray(static_cast<jsize>(raw.size()));
  if (array) env->SetByteArrayRegion(array, 0, static_cast<jsize>(raw.size()), raw.data());
  return array;
}
JNIEXPORT jlong JNICALL JNI_NAME(createReviewed)(JNIEnv*,jclass) {
  const auto config=default_config();if(!config)return 0;
  auto s=std::make_unique<State>();s->engine=std::make_unique<Engine>(config.value(), true, true);
  return reinterpret_cast<jlong>(s.release());
}
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
