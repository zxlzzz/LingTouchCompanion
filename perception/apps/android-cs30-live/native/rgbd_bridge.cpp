#include <jni.h>
#include <string>
#include <vector>
#include "lingtouch/config.h"
#include "lingtouch/depth_evidence.h"
#include "lingtouch/perception/pipeline.h"
#include "lingtouch/report_json.h"

namespace {
constexpr int width = 960, height = 540, pixels = width * height;
jstring bad(JNIEnv* env, const char* message) {
  env->ThrowNew(env->FindClass("java/lang/IllegalArgumentException"), message);
  return nullptr;
}
}

extern "C" JNIEXPORT jstring JNICALL
Java_com_lingtouch_cs30live_NativeRgbd_review(JNIEnv* env, jclass, jobjectArray depths,
                                            jlongArray times, jobjectArray object_masks) {
  using namespace lingtouch;
  const int count = env->GetArrayLength(depths);
  const int mask_count = env->GetArrayLength(object_masks);
  if (count < 1 || count > 3 || env->GetArrayLength(times) != count || mask_count > 32)
    return bad(env, "Invalid RGB-D replay frame count");
  auto defaults = default_config();
  if (!defaults) return bad(env, "Cannot load native configuration");
  Config config = defaults.value();
  config.depth.undistort = false;
  config.depth.image_mirrored = false;
  config.depth.meaning = DepthMeaning::kOpticalAxisZ;
  config.depth.wrap_window_radius_px = 0;
  config.depth.flying_abs_tolerance_mm = 20;
  config.depth.flying_rel_tolerance = .01;
  config.depth.flying_min_consistent_neighbors = 1;
  CameraIntrinsics camera;
  camera.width = width;
  camera.height = height;
  camera.fx = 465.5141296386719;
  camera.fy = 465.35321044921875;
  camera.cx = 488.48199462890625;
  camera.cy = 277.411376953125;
  camera.id = "cs30-viewer-aligned-960";
  DepthPipeline pipeline(config, true);
  if (!pipeline.set_intrinsics(camera)) return bad(env, "Invalid replay calibration");
  std::vector<std::vector<uint8_t>> masks;
  for (int i = 0; i < mask_count; ++i) {
    auto mask = static_cast<jbyteArray>(env->GetObjectArrayElement(object_masks, i));
    if (!mask || env->GetArrayLength(mask) != pixels) return bad(env, "Invalid YOLO mask");
    masks.emplace_back(pixels);
    env->GetByteArrayRegion(mask, 0, pixels, reinterpret_cast<jbyte*>(masks.back().data()));
    env->DeleteLocalRef(mask);
  }
  std::vector<jlong> timestamps(count);
  env->GetLongArrayRegion(times, 0, count, timestamps.data());
  std::vector<uint8_t> bytes(pixels * 2);
  std::vector<DepthFrame> history;
  for (int i = 0; i < count; ++i) {
    auto raw = static_cast<jbyteArray>(env->GetObjectArrayElement(depths, i));
    if (!raw || env->GetArrayLength(raw) != pixels * 2) return bad(env, "Expected aligned 960x540 RAW");
    env->GetByteArrayRegion(raw, 0, pixels * 2, reinterpret_cast<jbyte*>(bytes.data()));
    env->DeleteLocalRef(raw);
    DepthFrame f;
    f.width = width;
    f.height = height;
    f.frame_id = static_cast<uint64_t>(i + 1);
    f.capture_time_ns = timestamps[i];
    f.depth_mm.resize(pixels);
    for (int p = 0; p < pixels; ++p) f.depth_mm[p] = uint16_t(bytes[2*p] | (bytes[2*p+1] << 8));
    if (i + 1 == count) {
      const auto grid = pipeline.process(f, masks, &history);
      return env->NewStringUTF(depth_sim::evidence_json(grid, true).c_str());
    }
    history.push_back(std::move(f));
  }
  return bad(env, "No current frame");
}
