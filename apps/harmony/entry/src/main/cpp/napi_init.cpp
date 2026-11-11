// ArkTS（import core from 'libentry.so'）↔ 核心。只做转换，不放业务逻辑。
//
// 主路径：ArkTS 用 usbManager 执行启动表、用 usbSubmitTransfer 收等时包，每个传输回调
// 调一次 pushIsoTransfer（按批：一次 32 个微帧），不是每包一次跨层调用。
// 备选路径（真机清单里和主路径一起测）：usbManager.getFileDescriptor 拿 fd，交给 openFd，
// 由 native 的 libusb_wrap_sys_device 走和安卓相同的流程。
#include "napi/native_api.h"

#include <cstdint>
#include <cstring>
#include <memory>
#include <mutex>
#include <string>
#include <vector>

#include "../../../../../common/imu_input.h"
#include "lingtouch/config.h"
#include "lingtouch/engine.h"
#include "lingtouch/perception/cs30_protocol.h"
#include "lingtouch/perception/pipeline.h"
#include "lingtouch/report_json.h"
#ifdef LINGTOUCH_HARMONY_LIBUSB
#include "lingtouch/perception/cs30_libusb_source.h"
#endif

using namespace lingtouch;

namespace {

std::mutex g_mutex;
std::unique_ptr<Engine> g_engine;
ImuInput g_imu;
std::string g_last_error;
#ifdef LINGTOUCH_HARMONY_LIBUSB
std::unique_ptr<Cs30LibusbSource> g_libusb;
std::vector<std::string> g_libusb_log;
#endif

napi_value str(napi_env env, const std::string& s) {
  napi_value v;
  napi_create_string_utf8(env, s.c_str(), s.size(), &v);
  return v;
}

napi_value num(napi_env env, double d) {
  napi_value v;
  napi_create_double(env, d, &v);
  return v;
}

napi_value boolean(napi_env env, bool b) {
  napi_value v;
  napi_get_boolean(env, b, &v);
  return v;
}

napi_value undefined(napi_env env) {
  napi_value v;
  napi_get_undefined(env, &v);
  return v;
}

void set(napi_env env, napi_value obj, const char* key, napi_value value) {
  napi_set_named_property(env, obj, key, value);
}

bool get_args(napi_env env, napi_callback_info info, size_t expected, napi_value* argv) {
  size_t argc = expected;
  if (napi_get_cb_info(env, info, &argc, argv, nullptr, nullptr) != napi_ok || argc < expected) {
    napi_throw_error(env, nullptr, "参数个数不对");
    return false;
  }
  return true;
}

bool get_double(napi_env env, napi_value v, double* out) { return napi_get_value_double(env, v, out) == napi_ok; }

// ArrayBuffer 或 TypedArray（Uint8Array 等）→ 指针和字节数，不拷贝
bool get_bytes(napi_env env, napi_value v, const uint8_t** data, size_t* size) {
  bool is_ab = false;
  napi_is_arraybuffer(env, v, &is_ab);
  if (is_ab) {
    void* p = nullptr;
    if (napi_get_arraybuffer_info(env, v, &p, size) != napi_ok) return false;
    *data = static_cast<const uint8_t*>(p);
    return true;
  }
  bool is_ta = false;
  napi_is_typedarray(env, v, &is_ta);
  if (!is_ta) return false;
  napi_typedarray_type type;
  size_t length = 0, offset = 0;
  void* p = nullptr;
  napi_value ab;
  if (napi_get_typedarray_info(env, v, &type, &length, &p, &ab, &offset) != napi_ok) return false;
  size_t element = 1;
  if (type == napi_int16_array || type == napi_uint16_array) element = 2;
  if (type == napi_int32_array || type == napi_uint32_array || type == napi_float32_array) element = 4;
  if (type == napi_float64_array) element = 8;
  *data = static_cast<const uint8_t*>(p);
  *size = length * element;
  return true;
}

Engine* engine(napi_env env) {
  if (!g_engine) napi_throw_error(env, nullptr, "核心还没初始化，先调用 init()");
  return g_engine.get();
}

// init(): string —— 空串表示成功
napi_value Init(napi_env env, napi_callback_info) {
  std::lock_guard<std::mutex> lock(g_mutex);
  if (g_engine) return str(env, "");
  Result<Config> config = default_config();
  if (!config) return str(env, "默认参数有误：" + config.error());
  g_engine = std::make_unique<Engine>(config.value());
  return str(env, "");
}

napi_value StartImu(napi_env env, napi_callback_info) {
  const Status started = g_imu.start();
  return str(env, started.message);
}

napi_value StopImu(napi_env env, napi_callback_info) {
  g_imu.stop();
  return undefined(env);
}

napi_value PushImuNotify(napi_env env, napi_callback_info info) {
  const int64_t received_ns = monotonic_time_ns();
  napi_value argv[1];
  if (!get_args(env, info, 1, argv)) return nullptr;
  const uint8_t* data = nullptr;
  size_t size = 0;
  if (!get_bytes(env, argv[0], &data, &size)) {
    napi_throw_type_error(env, nullptr, "需要 IMU 通知原始字节");
    return nullptr;
  }
  g_imu.push(data, size, received_ns);
  return undefined(env);
}

napi_value LatestImu(napi_env env, napi_callback_info) {
  return str(env, g_imu.latest_text());
}

// protocolInfo(): { vendorId, productId, isoEndpoint, controlTimeoutMs, libusbAvailable }
napi_value ProtocolInfo(napi_env env, napi_callback_info) {
  napi_value o;
  napi_create_object(env, &o);
  set(env, o, "vendorId", num(env, cs30::kVendorId));
  set(env, o, "productId", num(env, cs30::kProductId));
  set(env, o, "isoEndpoint", num(env, cs30::kIsoEndpoint));
  set(env, o, "controlTimeoutMs", num(env, cs30::kControlTimeoutMs));
#ifdef LINGTOUCH_HARMONY_LIBUSB
  set(env, o, "libusbAvailable", boolean(env, true));
#else
  set(env, o, "libusbAvailable", boolean(env, false));
#endif
  return o;
}

napi_value StartupStepCount(napi_env env, napi_callback_info) {
  return num(env, static_cast<double>(Engine::startup_step_count()));
}

// startupStep(i): 启动表第 i 步（来自 perception/cs30/startup_sequence.json）
napi_value StartupStep(napi_env env, napi_callback_info info) {
  napi_value argv[1];
  if (!get_args(env, info, 1, argv)) return nullptr;
  double di = 0;
  if (!get_double(env, argv[0], &di) || di < 0 || di >= static_cast<double>(Engine::startup_step_count())) {
    napi_throw_range_error(env, nullptr, "步骤号越界");
    return nullptr;
  }
  const cs30::Step& s = Engine::startup_step(static_cast<size_t>(di));
  napi_value o;
  napi_create_object(env, &o);
  const char* kind = s.kind == cs30::StepKind::kControl ? "control" : s.kind == cs30::StepKind::kSetAlt ? "alt" : "queue_iso";
  set(env, o, "kind", str(env, kind));
  set(env, o, "isIn", boolean(env, s.is_in()));
  set(env, o, "requestType", num(env, s.request_type));
  set(env, o, "request", num(env, s.request));
  set(env, o, "value", num(env, s.value));
  set(env, o, "index", num(env, s.index));
  set(env, o, "length", num(env, s.length));
  napi_value data;
  void* p = nullptr;
  napi_create_arraybuffer(env, s.data_length, &p, &data);
  if (s.data_length) std::memcpy(p, s.data, s.data_length);
  set(env, o, "data", data);
  set(env, o, "interfaceNumber", num(env, s.interface_number));
  set(env, o, "altSetting", num(env, s.alt_setting));
  set(env, o, "isoTransfers", num(env, s.iso_transfers));
  set(env, o, "isoTransferBytes", num(env, s.iso_transfer_bytes));
  set(env, o, "isoPackets", num(env, s.iso_packets));
  set(env, o, "isoTimeoutMs", num(env, s.iso_timeout_ms));
  set(env, o, "settleMs", num(env, s.settle_ms));
  return o;
}

// onStartupResponse(i, data): string —— IN 请求的设备返回值；空串表示成功
napi_value OnStartupResponse(napi_env env, napi_callback_info info) {
  napi_value argv[2];
  if (!get_args(env, info, 2, argv)) return nullptr;
  Engine* e = engine(env);
  if (!e) return nullptr;
  double di = 0;
  const uint8_t* data = nullptr;
  size_t size = 0;
  if (!get_double(env, argv[0], &di) || di < 0 || !get_bytes(env, argv[1], &data, &size))
    return str(env, "参数不对");
  Status s = e->on_startup_response(static_cast<size_t>(di), data, size);
  return str(env, s ? "" : s.message);
}

napi_value FinishStartup(napi_env env, napi_callback_info) {
  Engine* e = engine(env);
  if (!e) return nullptr;
  Status s = e->finish_startup();
  return str(env, s ? "" : s.message);
}

napi_value ResetStream(napi_env env, napi_callback_info) {
  Engine* e = engine(env);
  if (!e) return nullptr;
  e->reset_stream();
  return undefined(env);
}

// pushIsoTransfer(buffer, descs): 一个等时传输的全部微帧。
// descs 是 Int32Array，每 3 个数一组 [申请长度, 实际长度, 状态]，第 i 个包从前面各包申请长度之和处开始。
napi_value PushIsoTransfer(napi_env env, napi_callback_info info) {
  napi_value argv[2];
  if (!get_args(env, info, 2, argv)) return nullptr;
  Engine* e = engine(env);
  if (!e) return nullptr;
  const uint8_t* buffer = nullptr;
  size_t buffer_size = 0;
  const uint8_t* desc_bytes = nullptr;
  size_t desc_size = 0;
  if (!get_bytes(env, argv[0], &buffer, &buffer_size) || !get_bytes(env, argv[1], &desc_bytes, &desc_size)) {
    napi_throw_type_error(env, nullptr, "pushIsoTransfer(ArrayBuffer, Int32Array)");
    return nullptr;
  }
  const size_t count = desc_size / (3 * sizeof(int32_t));
  std::vector<IsoPacketDesc> descs(count);
  for (size_t k = 0; k < count; ++k) {
    int32_t t[3];
    std::memcpy(t, desc_bytes + k * sizeof(t), sizeof(t));
    descs[k] = IsoPacketDesc{static_cast<uint32_t>(t[0] < 0 ? 0 : t[0]), static_cast<uint32_t>(t[1] < 0 ? 0 : t[1]), t[2]};
  }
  e->push_iso_transfer(buffer, buffer_size, descs.data(), descs.size());
  return undefined(env);
}

napi_value GridJson(napi_env env, napi_callback_info) {
  Engine* e = engine(env);
  return e ? str(env, grid_json(e->latest_grid(), monotonic_now_ns())) : nullptr;
}

napi_value StatsJson(napi_env env, napi_callback_info) {
  Engine* e = engine(env);
  return e ? str(env, stats_json(e->stats())) : nullptr;
}

napi_value DeviceSummary(napi_env env, napi_callback_info) {
  Engine* e = engine(env);
  return e ? str(env, e->device_summary()) : nullptr;
}

napi_value ConfigText(napi_env env, napi_callback_info) {
  Engine* e = engine(env);
  return e ? str(env, format_config(e->config())) : nullptr;
}

// 0 = 配置里没设定（待 Hsinlung 定），1 = flat，2 = raised
napi_value ConfigUnknownPolicy(napi_env env, napi_callback_info) {
  Engine* e = engine(env);
  if (!e) return nullptr;
  const auto& p = e->config().tactile.unknown_cell_policy;
  return num(env, p ? static_cast<double>(*p) : 0);
}

// encodeLatest(policy): ArrayBuffer（15 字节）或 undefined（原因见 lastError()）
napi_value EncodeLatest(napi_env env, napi_callback_info info) {
  napi_value argv[1];
  if (!get_args(env, info, 1, argv)) return nullptr;
  Engine* e = engine(env);
  if (!e) return nullptr;
  double policy = 0;
  get_double(env, argv[0], &policy);
  Result<LegacyFrame> f = e->encode_legacy(e->latest_grid(), static_cast<UnknownCellPolicy>(static_cast<int>(policy)));
  if (!f) {
    std::lock_guard<std::mutex> lock(g_mutex);
    g_last_error = f.error();
    return undefined(env);
  }
  napi_value out;
  void* p = nullptr;
  napi_create_arraybuffer(env, kLegacyFrameBytes, &p, &out);
  std::memcpy(p, f.value().data(), kLegacyFrameBytes);
  return out;
}

napi_value LastError(napi_env env, napi_callback_info) {
  std::lock_guard<std::mutex> lock(g_mutex);
  return str(env, g_last_error);
}

napi_value PlaneCheck(napi_env env, napi_callback_info) {
  Engine* e = engine(env);
  if (!e) return nullptr;
  DepthFrame frame;
  if (!e->latest_frame(&frame)) return str(env, "还没有收到帧");
  const std::optional<CameraIntrinsics> in = e->intrinsics();
  if (!in) return str(env, "没有可用内参");
  return str(env, format_plane_check(check_planarity(frame, *in, e->config().depth, 0.5)));
}

bool get_string(napi_env env, napi_value v, std::string* out) {
  size_t len = 0;
  if (napi_get_value_string_utf8(env, v, nullptr, 0, &len) != napi_ok) return false;
  std::string s(len, '\0');
  if (napi_get_value_string_utf8(env, v, &s[0], len + 1, &len) != napi_ok) return false;
  s.resize(len);
  *out = s;
  return true;
}

// saveLatestFrame(path): string —— 真机验收第 1 条；空串表示成功
napi_value SaveLatestFrame(napi_env env, napi_callback_info info) {
  napi_value argv[1];
  if (!get_args(env, info, 1, argv)) return nullptr;
  Engine* e = engine(env);
  if (!e) return nullptr;
  std::string path;
  if (!get_string(env, argv[0], &path)) return str(env, "参数不对");
  Status s = e->save_latest_frame(path);
  return str(env, s ? "" : s.message);
}

// processFrameFile(path): string —— 栅格 JSON（含 digest）；失败时 {"error": …}。真机验收第 3 条
napi_value ProcessFrameFile(napi_env env, napi_callback_info info) {
  napi_value argv[1];
  if (!get_args(env, info, 1, argv)) return nullptr;
  Engine* e = engine(env);
  if (!e) return nullptr;
  std::string path;
  if (!get_string(env, argv[0], &path)) return str(env, "{\"error\":\"参数不对\"}");
  Result<OccupancyGrid> g = e->process_frame_file(path);
  if (!g) return str(env, "{\"error\":\"" + json_escape(g.error()) + "\"}");
  return str(env, grid_json(g.value(), g.value().capture_time_ns));
}

// ---- 备选路径：getFileDescriptor + libusb_wrap_sys_device ----

// openFd(fd): string —— 空串表示已开流
napi_value OpenFd(napi_env env, napi_callback_info info) {
  napi_value argv[1];
  if (!get_args(env, info, 1, argv)) return nullptr;
#ifdef LINGTOUCH_HARMONY_LIBUSB
  Engine* e = engine(env);
  if (!e) return nullptr;
  double fd = -1;
  get_double(env, argv[0], &fd);
  std::lock_guard<std::mutex> lock(g_mutex);
  g_libusb.reset();
  g_libusb_log.clear();
  auto source = Cs30LibusbSource::open_fd(static_cast<int>(fd), e, [](const std::string& m) { g_libusb_log.push_back(m); });
  if (!source) return str(env, source.error());
  Status s = source.value()->start();
  if (!s) return str(env, s.message);
  g_libusb = std::move(source.value());
  return str(env, "");
#else
  (void)argv;
  return str(env, "这次编译没有包含 libusb（LINGTOUCH_HARMONY_LIBUSB=OFF）");
#endif
}

napi_value CloseFd(napi_env env, napi_callback_info) {
#ifdef LINGTOUCH_HARMONY_LIBUSB
  std::lock_guard<std::mutex> lock(g_mutex);
  g_libusb.reset();
#endif
  return undefined(env);
}

napi_value LibusbLog(napi_env env, napi_callback_info) {
  std::string all;
#ifdef LINGTOUCH_HARMONY_LIBUSB
  std::lock_guard<std::mutex> lock(g_mutex);
  for (const std::string& line : g_libusb_log) all += line + "\n";
#endif
  return str(env, all);
}

}  // namespace

EXTERN_C_START
static napi_value RegisterExports(napi_env env, napi_value exports) {
  napi_property_descriptor desc[] = {
      {"init", nullptr, Init, nullptr, nullptr, nullptr, napi_default, nullptr},
      {"startImu", nullptr, StartImu, nullptr, nullptr, nullptr, napi_default, nullptr},
      {"stopImu", nullptr, StopImu, nullptr, nullptr, nullptr, napi_default, nullptr},
      {"pushImuNotify", nullptr, PushImuNotify, nullptr, nullptr, nullptr, napi_default, nullptr},
      {"latestImu", nullptr, LatestImu, nullptr, nullptr, nullptr, napi_default, nullptr},
      {"protocolInfo", nullptr, ProtocolInfo, nullptr, nullptr, nullptr, napi_default, nullptr},
      {"startupStepCount", nullptr, StartupStepCount, nullptr, nullptr, nullptr, napi_default, nullptr},
      {"startupStep", nullptr, StartupStep, nullptr, nullptr, nullptr, napi_default, nullptr},
      {"onStartupResponse", nullptr, OnStartupResponse, nullptr, nullptr, nullptr, napi_default, nullptr},
      {"finishStartup", nullptr, FinishStartup, nullptr, nullptr, nullptr, napi_default, nullptr},
      {"resetStream", nullptr, ResetStream, nullptr, nullptr, nullptr, napi_default, nullptr},
      {"pushIsoTransfer", nullptr, PushIsoTransfer, nullptr, nullptr, nullptr, napi_default, nullptr},
      {"gridJson", nullptr, GridJson, nullptr, nullptr, nullptr, napi_default, nullptr},
      {"statsJson", nullptr, StatsJson, nullptr, nullptr, nullptr, napi_default, nullptr},
      {"deviceSummary", nullptr, DeviceSummary, nullptr, nullptr, nullptr, napi_default, nullptr},
      {"configText", nullptr, ConfigText, nullptr, nullptr, nullptr, napi_default, nullptr},
      {"configUnknownPolicy", nullptr, ConfigUnknownPolicy, nullptr, nullptr, nullptr, napi_default, nullptr},
      {"encodeLatest", nullptr, EncodeLatest, nullptr, nullptr, nullptr, napi_default, nullptr},
      {"lastError", nullptr, LastError, nullptr, nullptr, nullptr, napi_default, nullptr},
      {"planeCheck", nullptr, PlaneCheck, nullptr, nullptr, nullptr, napi_default, nullptr},
      {"saveLatestFrame", nullptr, SaveLatestFrame, nullptr, nullptr, nullptr, napi_default, nullptr},
      {"processFrameFile", nullptr, ProcessFrameFile, nullptr, nullptr, nullptr, napi_default, nullptr},
      {"openFd", nullptr, OpenFd, nullptr, nullptr, nullptr, napi_default, nullptr},
      {"closeFd", nullptr, CloseFd, nullptr, nullptr, nullptr, napi_default, nullptr},
      {"libusbLog", nullptr, LibusbLog, nullptr, nullptr, nullptr, napi_default, nullptr},
  };
  napi_define_properties(env, exports, sizeof(desc) / sizeof(desc[0]), desc);
  return exports;
}
EXTERN_C_END

static napi_module g_module = {1, 0, nullptr, RegisterExports, "entry", nullptr, {nullptr}};

extern "C" __attribute__((constructor)) void RegisterEntryModule(void) { napi_module_register(&g_module); }
