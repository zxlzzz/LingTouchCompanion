#include "cs30_sensor_adapter.h"
#include <utility>
namespace lingtouch {
AndroidCs30SensorAdapter::AndroidCs30SensorAdapter(std::unique_ptr<CameraUsbTransport> t,
    Cs30CaptureSession::FrameSink f, Cs30CaptureSession::ResetSink r)
    : session_(std::move(t),std::move(f),std::move(r)) {}
CameraStatus AndroidCs30SensorAdapter::find_devices(std::vector<std::string>& v) { return session_.find_devices(v); }
CameraStatus AndroidCs30SensorAdapter::open_device(const std::string& id,EventCallback cb) { return session_.open_device(id,std::move(cb)); }
CameraStatus AndroidCs30SensorAdapter::get_stream_profiles(std::vector<CameraStreamProfile>& v) { return session_.get_stream_profiles(v); }
CameraStatus AndroidCs30SensorAdapter::start_streaming(const CameraStreamProfile& p) { return session_.start_streaming(p); }
CameraStatus AndroidCs30SensorAdapter::get_calibration(std::shared_ptr<const CameraCalibration>& c) { return session_.get_calibration(c); }
CameraStatus AndroidCs30SensorAdapter::get_capture_settings(CameraCaptureSettings& s) { return session_.get_capture_settings(s); }
CameraStatus AndroidCs30SensorAdapter::get_latest_frame(uint64_t after,FrameBundle& f) { return session_.get_latest_frame(after,f); }
CameraStatus AndroidCs30SensorAdapter::stop_streaming() { return session_.stop_streaming(); }
CameraStatus AndroidCs30SensorAdapter::close_device() { return session_.close_device(); }
} // namespace lingtouch
