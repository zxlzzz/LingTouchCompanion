#include "cs30_sensor_adapter.h"
#include <utility>
namespace lingtouch {
HarmonyCs30SensorAdapter::HarmonyCs30SensorAdapter(std::unique_ptr<CameraUsbTransport> t,
    Cs30CaptureSession::FrameSink f, Cs30CaptureSession::ResetSink r)
    : session_(std::move(t),std::move(f),std::move(r)) {}
CameraStatus HarmonyCs30SensorAdapter::find_devices(std::vector<std::string>& v) { return session_.find_devices(v); }
CameraStatus HarmonyCs30SensorAdapter::open_device(const std::string& id,EventCallback cb) { return session_.open_device(id,std::move(cb)); }
CameraStatus HarmonyCs30SensorAdapter::get_stream_profiles(std::vector<CameraStreamProfile>& v) { return session_.get_stream_profiles(v); }
CameraStatus HarmonyCs30SensorAdapter::start_streaming(const CameraStreamProfile& p) { return session_.start_streaming(p); }
CameraStatus HarmonyCs30SensorAdapter::get_calibration(std::shared_ptr<const CameraCalibration>& c) { return session_.get_calibration(c); }
CameraStatus HarmonyCs30SensorAdapter::get_capture_settings(CameraCaptureSettings& s) { return session_.get_capture_settings(s); }
CameraStatus HarmonyCs30SensorAdapter::get_latest_frame(uint64_t after,FrameBundle& f) { return session_.get_latest_frame(after,f); }
CameraStatus HarmonyCs30SensorAdapter::stop_streaming() { return session_.stop_streaming(); }
CameraStatus HarmonyCs30SensorAdapter::close_device() { return session_.close_device(); }
} // namespace lingtouch
