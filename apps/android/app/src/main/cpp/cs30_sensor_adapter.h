#pragma once
#include "lingtouch/perception/cs30_capture.h"
namespace lingtouch {
class AndroidCs30SensorAdapter final : public SensorAdapter {
 public:
  explicit AndroidCs30SensorAdapter(std::unique_ptr<CameraUsbTransport> transport,
      Cs30CaptureSession::FrameSink sink = {}, Cs30CaptureSession::ResetSink reset = {});
  CameraStatus find_devices(std::vector<std::string>&) override;
  CameraStatus open_device(const std::string&, EventCallback = {}) override;
  CameraStatus get_stream_profiles(std::vector<CameraStreamProfile>&) override;
  CameraStatus start_streaming(const CameraStreamProfile&) override;
  CameraStatus get_calibration(std::shared_ptr<const CameraCalibration>&) override;
  CameraStatus get_capture_settings(CameraCaptureSettings&) override;
  CameraStatus get_latest_frame(uint64_t, FrameBundle&) override;
  CameraStatus stop_streaming() override;
  CameraStatus close_device() override;
  bool receiving() const { return session_.receiving(); }
  std::string diagnostics() const { return session_.diagnostics(); }
 private:
  Cs30CaptureSession session_;
};
} // namespace lingtouch
