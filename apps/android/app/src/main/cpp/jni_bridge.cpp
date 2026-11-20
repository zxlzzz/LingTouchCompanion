// Kotlin（com.lingtouch.companion.NativeCore）↔ 核心。只做转换，不放业务逻辑。
#include <jni.h>

#include <cstdio>
#include <deque>
#include <memory>
#include <mutex>
#include <string>

#ifdef __ANDROID__
#include <android/log.h>
#endif

#include "../../../../../common/imu_input.h"
#include "lingtouch/config.h"
#include "lingtouch/engine.h"
#include "android_usb_transport.h"
#include "cs30_sensor_adapter.h"
#include "lingtouch/perception/pipeline.h"
#include "lingtouch/report_json.h"

using namespace lingtouch;

namespace {

// 最近的取流日志，界面直接显示，排查不依赖 adb
std::mutex g_log_mutex;
std::deque<std::string> g_log;

void log_line(const std::string& message) {
  {
    std::lock_guard<std::mutex> lock(g_log_mutex);
    g_log.push_back(message);
    if (g_log.size() > 60) g_log.pop_front();
  }
#ifdef __ANDROID__
  __android_log_print(ANDROID_LOG_INFO, "LingTouchCore", "%s", message.c_str());
#else
  std::fprintf(stderr, "[LingTouchCore] %s\n", message.c_str());
#endif
}

struct NativeState {
  std::unique_ptr<Engine> engine;
  ImuInput imu;
  std::mutex camera_mutex;
  std::unique_ptr<AndroidCs30SensorAdapter> camera;
  CameraStreamProfile camera_profile;
  CameraStatus camera_status;
  bool camera_receiving=false;
  std::shared_ptr<const FrameBundle> preview_frame;
  uint64_t preview_epoch=0;
  std::string camera_diagnostics="相机未连接";
  std::mutex error_mutex;
  std::string last_error;

  void set_error(const std::string& e) {
    std::lock_guard<std::mutex> lock(error_mutex);
    last_error = e;
  }
  void set_camera_status(const CameraStatus& status,bool receiving=false) {
    std::lock_guard<std::mutex> lock(error_mutex);camera_status=status;camera_receiving=receiving;
    if(!receiving)preview_frame.reset();
  }
  void reset_capture() {
    engine->reset_stream();
    std::lock_guard<std::mutex> lock(error_mutex);
    preview_frame.reset();camera_receiving=false;++preview_epoch;
  }
};

class JniUsbHost {
 public:
  JavaVM* vm=nullptr;
  jobject host=nullptr;
  jmethodID list=nullptr,authorized=nullptr,open=nullptr,close=nullptr;
  struct Scope {
    JavaVM* vm;JNIEnv* env=nullptr;bool attached=false;
    explicit Scope(JavaVM* v):vm(v) {
      if(vm->GetEnv(reinterpret_cast<void**>(&env),JNI_VERSION_1_6)==JNI_EDETACHED) {
#ifdef __ANDROID__
        attached=vm->AttachCurrentThread(&env,nullptr)==JNI_OK;
#else
        attached=vm->AttachCurrentThread(reinterpret_cast<void**>(&env),nullptr)==JNI_OK;
#endif
      }
    }
    ~Scope(){if(attached)vm->DetachCurrentThread();}
  };
  ~JniUsbHost(){Scope scope(vm);if(scope.env && host)scope.env->DeleteGlobalRef(host);}
  bool initialize(JNIEnv* env,jobject object) {
    env->GetJavaVM(&vm);host=env->NewGlobalRef(object);
    jclass type=env->GetObjectClass(object);
    list=env->GetMethodID(type,"usbDeviceIds","()[Ljava/lang/String;");
    authorized=env->GetMethodID(type,"usbAuthorized","(Ljava/lang/String;)Z");
    open=env->GetMethodID(type,"usbOpenFd","(Ljava/lang/String;)I");
    close=env->GetMethodID(type,"usbCloseFd","()V");env->DeleteLocalRef(type);
    if(env->ExceptionCheck()){env->ExceptionClear();return false;}
    return host && list && authorized && open && close;
  }
  CameraStatus enumerate(std::vector<CameraUsbDevice>& devices) {
    Scope scope(vm);auto* env=scope.env;
    if(!env)return {CameraCode::kIoError,"无法访问 Android USB 服务"};
    auto ids=static_cast<jobjectArray>(env->CallObjectMethod(host,list));
    if(env->ExceptionCheck()){env->ExceptionClear();return {CameraCode::kIoError,"枚举 Android USB 设备失败"};}
    std::vector<CameraUsbDevice> found;
    if(ids)for(jsize i=0;i<env->GetArrayLength(ids);++i) {
      auto id=static_cast<jstring>(env->GetObjectArrayElement(ids,i));
      const char* text=env->GetStringUTFChars(id,nullptr);
      if(!text){env->DeleteLocalRef(id);env->DeleteLocalRef(ids);return {CameraCode::kIoError,"读取 USB 设备 ID 失败"};}
      std::string name=text;env->ReleaseStringUTFChars(id,text);
      const bool allowed=env->CallBooleanMethod(host,authorized,id)==JNI_TRUE;
      env->DeleteLocalRef(id);
      if(env->ExceptionCheck()){env->ExceptionClear();env->DeleteLocalRef(ids);return {CameraCode::kIoError,"检查 USB 授权失败"};}
      found.push_back({std::move(name),allowed});
    }
    if(ids)env->DeleteLocalRef(ids);devices=std::move(found);return {};
  }
  CameraStatus open_fd(const std::string& id,int& fd) {
    Scope scope(vm);auto* env=scope.env;
    if(!env)return {CameraCode::kOpenFailed,"Android USB 服务不可用"};
    const auto value=env->NewStringUTF(id.c_str());
    const int result=env->CallIntMethod(host,open,value);env->DeleteLocalRef(value);
    if(env->ExceptionCheck()){env->ExceptionClear();return {CameraCode::kOpenFailed,"Android 打开 USB 连接异常"};}
    if(result==-2)return {CameraCode::kPermissionDenied,"USB 尚未授权，请在前台重新连接并授权"};
    if(result==-3)return {CameraCode::kDeviceNotFound,"USB 设备已移除，请重新枚举"};
    if(result<0)return {CameraCode::kOpenFailed,"无法打开或接管 USB 接口，请检查占用、线材和供电"};
    fd=result;return {};
  }
  void close_fd() {
    Scope scope(vm);if(!scope.env)return;scope.env->CallVoidMethod(host,close);
    if(scope.env->ExceptionCheck())scope.env->ExceptionClear();
  }
};

NativeState* state(jlong handle) { return reinterpret_cast<NativeState*>(handle); }

jstring to_jstring(JNIEnv* env, const std::string& s) { return env->NewStringUTF(s.c_str()); }

std::string& create_error() {
  static std::string e;
  return e;
}

}  // namespace

extern "C" {

JNIEXPORT jlong JNICALL Java_com_lingtouch_companion_NativeCore_nativeCreate(JNIEnv*, jclass) {
  Result<Config> config = default_config();
  if (!config) {
    create_error() = "默认参数有误：" + config.error();
    log_line(create_error());
    return 0;
  }
  auto* s = new NativeState();
  s->engine = std::make_unique<Engine>(config.value());
  return reinterpret_cast<jlong>(s);
}

JNIEXPORT jstring JNICALL Java_com_lingtouch_companion_NativeCore_nativeCreateError(JNIEnv* env, jclass) {
  return to_jstring(env, create_error());
}

JNIEXPORT void JNICALL Java_com_lingtouch_companion_NativeCore_nativeDestroy(JNIEnv*, jclass, jlong handle) {
  NativeState* s = state(handle);
  if (s == nullptr) return;
  {
    std::lock_guard<std::mutex> lock(s->camera_mutex);
    s->camera.reset();
  }
  delete s;
}

JNIEXPORT jlong JNICALL Java_com_lingtouch_companion_NativeCore_nativeImuTimeNs(JNIEnv*, jclass) {
  return monotonic_time_ns();
}

JNIEXPORT jstring JNICALL Java_com_lingtouch_companion_NativeCore_nativeStartImu(JNIEnv* env, jclass, jlong handle) {
  const Status started = state(handle)->imu.start();
  return started ? nullptr : to_jstring(env, started.message);
}

JNIEXPORT void JNICALL Java_com_lingtouch_companion_NativeCore_nativeStopImu(JNIEnv*, jclass, jlong handle) {
  state(handle)->imu.stop();
}

JNIEXPORT void JNICALL Java_com_lingtouch_companion_NativeCore_nativePushImuNotify(
    JNIEnv* env, jclass, jlong handle, jbyteArray bytes, jlong received_ns) {
  const jsize size = env->GetArrayLength(bytes);
  if (size == 0) return;
  jbyte* data = env->GetByteArrayElements(bytes, nullptr);
  if (data == nullptr) return;
  state(handle)->imu.push(reinterpret_cast<const uint8_t*>(data), static_cast<size_t>(size), received_ns);
  env->ReleaseByteArrayElements(bytes, data, JNI_ABORT);
}

JNIEXPORT jstring JNICALL Java_com_lingtouch_companion_NativeCore_nativeLatestImu(JNIEnv* env, jclass, jlong handle) {
  return to_jstring(env, state(handle)->imu.latest_text());
}

// 返回 null 表示成功，否则是错误说明。fd 来自 UsbDeviceConnection.getFileDescriptor()，由 Kotlin 侧关闭。
JNIEXPORT jstring JNICALL Java_com_lingtouch_companion_NativeCore_nativeOpenCamera(JNIEnv* env, jclass, jlong handle,
                                                                                   jobject host,jstring device_id,
                                                                                   jboolean with_color) {
  NativeState* s = state(handle);
  std::lock_guard<std::mutex> lock(s->camera_mutex);
  s->camera.reset();
  s->reset_capture();
  auto platform=std::make_shared<JniUsbHost>();
  if(!platform->initialize(env,host))return to_jstring(env,"USB 平台桥接初始化失败");
  AndroidUsbHost callbacks;
  callbacks.enumerate=[platform](auto& out){return platform->enumerate(out);};
  callbacks.open_fd=[platform](const auto& id,int& fd){return platform->open_fd(id,fd);};
  callbacks.close_fd=[platform]{platform->close_fd();};callbacks.log=log_line;
  s->camera=std::make_unique<AndroidCs30SensorAdapter>(std::make_unique<AndroidUsbTransport>(std::move(callbacks)),
      [s](const FrameBundle& frame){
        const auto result=s->engine->submit_frame(frame);
        if(result) {
          auto snapshot=std::make_shared<const FrameBundle>(frame);
          std::lock_guard<std::mutex> lock(s->error_mutex);
          s->camera_status={CameraCode::kOk,frame.color?"正在接收深度和彩色":"正在接收深度"};
          s->camera_receiving=true;s->preview_frame=std::move(snapshot);
        } else s->set_camera_status({CameraCode::kStreamInterrupted,result.message});
      },[s]{s->reset_capture();});
  const char* raw=env->GetStringUTFChars(device_id,nullptr);
  if(!raw){s->camera.reset();return to_jstring(env,"无法读取设备 ID");}
  const std::string id=raw;env->ReleaseStringUTFChars(device_id,raw);
  std::vector<std::string> ids;auto started=s->camera->find_devices(ids);
  if(started)started=s->camera->open_device(id,[s](const CameraStatus& status){s->set_camera_status(status);log_line(status.message);});
  s->camera_profile={with_color?CameraStreamMode::kDepthRgb:CameraStreamMode::kDepth,{640,480},std::nullopt};
  if(with_color)s->camera_profile.color=CameraResolution{960,540};
  s->set_camera_status({CameraCode::kOk,"已发起取流，等待完整帧和标定"});
  if(started)started=s->camera->start_streaming(s->camera_profile);
  if(!started){s->set_camera_status(started);log_line(started.message);s->camera.reset();return to_jstring(env,started.message);}
  std::shared_ptr<const CameraCalibration> calibration;
  const auto calibration_status=s->camera->get_calibration(calibration);
  if(!calibration_status) {
    std::lock_guard<std::mutex> error(s->error_mutex);
    if(s->camera_status.code==CameraCode::kOk)s->camera_status=calibration_status;
  }
  log_line(s->camera->diagnostics());
  return nullptr;
}

JNIEXPORT jstring JNICALL Java_com_lingtouch_companion_NativeCore_nativeUsbLog(JNIEnv* env, jclass) {
  std::lock_guard<std::mutex> lock(g_log_mutex);
  std::string text;
  for (const std::string& line : g_log) text += line + "\n";
  return to_jstring(env, text);
}

JNIEXPORT void JNICALL Java_com_lingtouch_companion_NativeCore_nativeCloseCamera(JNIEnv*, jclass, jlong handle) {
  NativeState* s = state(handle);
  std::lock_guard<std::mutex> lock(s->camera_mutex);
  if(s->camera)log_line("停止采集："+s->camera->diagnostics());
  s->camera.reset();  // 停流、release；fd 由 Kotlin 侧随后关闭
  s->reset_capture();
  s->set_camera_status({CameraCode::kOk,"未连接"});
}

JNIEXPORT jstring JNICALL Java_com_lingtouch_companion_NativeCore_nativeResetCamera(JNIEnv* env, jclass, jlong handle) {
  NativeState* s = state(handle);
  std::lock_guard<std::mutex> lock(s->camera_mutex);
  if (!s->camera) return to_jstring(env, "相机没有打开");
  CameraStatus r=s->camera->stop_streaming();
  s->set_camera_status({CameraCode::kOk,"已发起取流，等待完整帧和标定"});
  if(r)r=s->camera->start_streaming(s->camera_profile);
  if(!r)s->set_camera_status(r);
  return r ? nullptr : to_jstring(env, r.message);
}

JNIEXPORT jboolean JNICALL Java_com_lingtouch_companion_NativeCore_nativeCameraStreaming(JNIEnv*, jclass,
                                                                                         jlong handle) {
  NativeState* s = state(handle);
  std::lock_guard<std::mutex> lock(s->error_mutex);
  return s->camera_receiving ? JNI_TRUE : JNI_FALSE;
}

JNIEXPORT jstring JNICALL Java_com_lingtouch_companion_NativeCore_nativeCameraStatus(JNIEnv* env,jclass,jlong handle) {
  auto* s=state(handle);std::lock_guard<std::mutex> lock(s->error_mutex);return to_jstring(env,s->camera_status.message);
}
JNIEXPORT jint JNICALL Java_com_lingtouch_companion_NativeCore_nativeCameraCode(JNIEnv*,jclass,jlong handle) {
  auto* s=state(handle);std::lock_guard<std::mutex> lock(s->error_mutex);return jint(s->camera_status.code);
}

JNIEXPORT jlong JNICALL Java_com_lingtouch_companion_NativeCore_nativeCameraEpoch(JNIEnv*,jclass,jlong handle) {
  auto* s=state(handle);std::lock_guard<std::mutex> lock(s->error_mutex);return jlong(s->preview_epoch);
}

// Called on the service's serialized camera worker, never during teardown.
// Binary arrays avoid string/base64 conversions and JNI's array lengths are
// used as element counts; no Harmony NAPI TypedArray assumptions are shared.
JNIEXPORT jobject JNICALL Java_com_lingtouch_companion_NativeCore_nativeCameraPreview(
    JNIEnv* env,jclass,jlong handle,jlong after) {
  auto* s=state(handle);std::shared_ptr<const FrameBundle> frame;uint64_t epoch=0;
  {
    std::lock_guard<std::mutex> lock(s->error_mutex);
    if(!s->camera_receiving || !s->preview_frame || after<0 || s->preview_frame->depth.frame_id<=uint64_t(after))return nullptr;
    frame=s->preview_frame;epoch=s->preview_epoch;
  }
  const auto& depth=frame->depth;
  const int step=(depth.width+319)/320;
  const int w=(depth.width+step-1)/step,h=(depth.height+step-1)/step;
  std::vector<jint> argb(size_t(w)*h);
  for(int y=0;y<h;++y)for(int x=0;x<w;++x) {
    const uint32_t mm=depth.depth_mm[size_t(y*step)*depth.width+x*step];
    const uint32_t gray=mm>=100 && mm<=5000?255-(mm-100)*223/4900:0;
    argb[size_t(y)*w+x]=jint(0xff000000u|gray*0x010101u);
  }
  const auto jpeg=env->NewByteArray(frame->color?jsize(frame->color->jpeg.size()):0);
  if(!jpeg)return nullptr;
  if(frame->color)env->SetByteArrayRegion(jpeg,0,jsize(frame->color->jpeg.size()),
      reinterpret_cast<const jbyte*>(frame->color->jpeg.data()));
  const auto pixels=env->NewIntArray(jsize(argb.size()));
  if(!pixels)return nullptr;
  env->SetIntArrayRegion(pixels,0,jsize(argb.size()),argb.data());
  const auto type=env->FindClass("com/lingtouch/companion/CameraPreviewFrame");
  if(!type)return nullptr;
  const auto constructor=env->GetMethodID(type,"<init>","(JJ[B[III)V");
  return constructor?env->NewObject(type,constructor,jlong(epoch),jlong(depth.frame_id),jpeg,pixels,jint(w),jint(h)):nullptr;
}

JNIEXPORT jstring JNICALL Java_com_lingtouch_companion_NativeCore_nativeGridJson(JNIEnv* env, jclass, jlong handle) {
  return to_jstring(env, grid_json(state(handle)->engine->latest_grid(), monotonic_now_ns()));
}

JNIEXPORT jstring JNICALL Java_com_lingtouch_companion_NativeCore_nativeStatsJson(JNIEnv* env, jclass, jlong handle) {
  return to_jstring(env, stats_json(state(handle)->engine->stats()));
}

JNIEXPORT jstring JNICALL Java_com_lingtouch_companion_NativeCore_nativeDeviceSummary(JNIEnv* env, jclass,
                                                                                      jlong handle) {
  auto* s=state(handle);
  // UI polling must never wait behind a multi-second USB control request.
  std::unique_lock<std::mutex> camera(s->camera_mutex,std::try_to_lock);
  if(camera.owns_lock()) {
    const std::string snapshot=s->camera?s->camera->diagnostics():"相机未连接";
    std::lock_guard<std::mutex> error(s->error_mutex);s->camera_diagnostics=snapshot;
  }
  std::lock_guard<std::mutex> error(s->error_mutex);return to_jstring(env,s->camera_diagnostics);
}

// 0 = 配置里没设定（待 Hsinlung 定），1 = flat，2 = raised
JNIEXPORT jint JNICALL Java_com_lingtouch_companion_NativeCore_nativeConfigUnknownPolicy(JNIEnv*, jclass,
                                                                                         jlong handle) {
  const auto& p = state(handle)->engine->config().tactile.unknown_cell_policy;
  return p ? static_cast<jint>(*p) : 0;
}

JNIEXPORT jstring JNICALL Java_com_lingtouch_companion_NativeCore_nativeConfigText(JNIEnv* env, jclass, jlong handle) {
  return to_jstring(env, format_config(state(handle)->engine->config()));
}

// 最新栅格 → 15 字节旧板帧。policy 必须是 1（flat）或 2（raised），否则返回 null，原因见 nativeLastError。
JNIEXPORT jbyteArray JNICALL Java_com_lingtouch_companion_NativeCore_nativeEncodeLatest(JNIEnv* env, jclass,
                                                                                        jlong handle, jint policy) {
  NativeState* s = state(handle);
  Result<LegacyFrame> f = s->engine->encode_legacy(s->engine->latest_grid(), static_cast<UnknownCellPolicy>(policy));
  if (!f) {
    s->set_error(f.error());
    return nullptr;
  }
  jbyteArray out = env->NewByteArray(kLegacyFrameBytes);
  env->SetByteArrayRegion(out, 0, kLegacyFrameBytes, reinterpret_cast<const jbyte*>(f.value().data()));
  return out;
}

JNIEXPORT jstring JNICALL Java_com_lingtouch_companion_NativeCore_nativeLastError(JNIEnv* env, jclass, jlong handle) {
  NativeState* s = state(handle);
  std::lock_guard<std::mutex> lock(s->error_mutex);
  return to_jstring(env, s->last_error);
}

// 对最近一帧做平面检查（对着平整的墙或斜看地面时用）
JNIEXPORT jstring JNICALL Java_com_lingtouch_companion_NativeCore_nativePlaneCheck(JNIEnv* env, jclass, jlong handle) {
  Engine& e = *state(handle)->engine;
  DepthFrame frame;
  if (!e.latest_frame(&frame)) return to_jstring(env, "还没有收到帧");
  const std::optional<CameraIntrinsics> in = e.intrinsics();
  if (!in) return to_jstring(env, "没有可用内参");
  return to_jstring(env, format_plane_check(check_planarity(frame, *in, e.config().depth, 0.5)));
}

// 把最近一帧原始深度存到 path（真机验收第 1 条：拿到电脑上与厂家 SDK 的帧比对）
JNIEXPORT jstring JNICALL Java_com_lingtouch_companion_NativeCore_nativeSaveLatestFrame(JNIEnv* env, jclass,
                                                                                        jlong handle, jstring path) {
  const char* p = env->GetStringUTFChars(path, nullptr);
  const std::string file(p);
  env->ReleaseStringUTFChars(path, p);
  Status s = state(handle)->engine->save_latest_frame(file);
  return s ? nullptr : to_jstring(env, s.message);
}

// 对帧文件算栅格（真机验收第 3 条：两个平台、电脑比对摘要）。返回栅格 JSON，失败时返回 {"error": …}
JNIEXPORT jstring JNICALL Java_com_lingtouch_companion_NativeCore_nativeProcessFrameFile(JNIEnv* env, jclass,
                                                                                         jlong handle, jstring path) {
  const char* p = env->GetStringUTFChars(path, nullptr);
  const std::string file(p);
  env->ReleaseStringUTFChars(path, p);
  Result<OccupancyGrid> g = state(handle)->engine->process_frame_file(file);
  if (!g) return to_jstring(env, "{\"error\":\"" + json_escape(g.error()) + "\"}");
  return to_jstring(env, grid_json(g.value(), g.value().capture_time_ns));
}

}  // extern "C"
