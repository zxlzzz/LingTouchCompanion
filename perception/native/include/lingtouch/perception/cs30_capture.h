#pragma once

#include <condition_variable>
#include <functional>
#include <memory>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

#include "lingtouch/modules.h"
#include "lingtouch/perception/cs30_protocol.h"
#include "lingtouch/perception/uvc_frame_assembler.h"

namespace lingtouch {

// Platform code owns USB permission and the system connection. A transport must
// finish every packet/event callback before stop_iso()/close() returns.
struct CameraUsbDevice {
  std::string id;
  bool authorized = false;
};

struct CameraUsbControl {
  uint8_t request_type = 0;
  uint8_t request = 0;
  uint16_t value = 0;
  uint16_t index = 0;
  uint16_t length = 0;
  uint32_t timeout_ms = cs30::kControlTimeoutMs;
  std::vector<uint8_t> data;
};

struct CameraIsoConfig {
  uint8_t endpoint = cs30::kIsoEndpoint;
  uint32_t transfers = 10;
  uint32_t packets = 32;
  uint32_t packet_bytes = cs30::kIsoPacketBytes;
  uint32_t timeout_ms = 5000;
};

class CameraUsbTransport {
 public:
  using PacketSink = std::function<void(const uint8_t*, size_t, const IsoPacketDesc*, size_t)>;
  using EventSink = SensorAdapter::EventCallback;
  virtual ~CameraUsbTransport() = default;
  virtual CameraStatus enumerate(std::vector<CameraUsbDevice>& devices) = 0;
  virtual CameraStatus open(const std::string& id) = 0;
  virtual CameraStatus claim(int interface_number) = 0;
  virtual CameraStatus set_alt(int interface_number, int alternate) = 0;
  virtual CameraStatus control(const CameraUsbControl& request, std::vector<uint8_t>& response) = 0;
  virtual CameraStatus start_iso(const CameraIsoConfig&, PacketSink, EventSink) = 0;
  virtual CameraStatus stop_iso() = 0;
  virtual CameraStatus close() = 0;
};

// Shared capture mechanics; concrete SensorAdapter classes live in each app's
// cpp directory. This layer never performs visual inference or USB permission UI.
class Cs30CaptureSession {
 public:
  using FrameSink = std::function<void(const FrameBundle&)>;
  using ResetSink = std::function<void()>;
  explicit Cs30CaptureSession(std::unique_ptr<CameraUsbTransport> transport,
                              FrameSink frame_sink = {}, ResetSink reset_sink = {});
  ~Cs30CaptureSession();
  Cs30CaptureSession(const Cs30CaptureSession&) = delete;
  Cs30CaptureSession& operator=(const Cs30CaptureSession&) = delete;

  CameraStatus find_devices(std::vector<std::string>& ids);
  CameraStatus open_device(const std::string& id, SensorAdapter::EventCallback callback);
  CameraStatus get_stream_profiles(std::vector<CameraStreamProfile>& profiles);
  CameraStatus start_streaming(const CameraStreamProfile& profile);
  CameraStatus get_calibration(std::shared_ptr<const CameraCalibration>& calibration);
  CameraStatus get_capture_settings(CameraCaptureSettings& settings);
  CameraStatus get_latest_frame(uint64_t after_frame_id, FrameBundle& frame);
  CameraStatus stop_streaming();
  CameraStatus close_device();
  std::string diagnostics() const;
  bool receiving() const;

 private:
  CameraStatus execute_startup();
  CameraStatus load_calibration();
  void on_packets(uint64_t session, const uint8_t*, size_t, const IsoPacketDesc*, size_t);
  void on_payload(const uint8_t*, size_t);
  void on_event(uint64_t session, const CameraStatus& status);
  void clear_stream_locked();
  void stop_monitor();

  std::unique_ptr<CameraUsbTransport> transport_;
  FrameSink frame_sink_;
  ResetSink reset_sink_;
  mutable std::mutex mutex_;
  std::mutex delivery_mutex_;
  std::condition_variable monitor_cv_;
  std::thread monitor_;
  bool monitoring_ = false;
  int64_t last_frame_ns_ = 0;
  size_t max_payload_bytes_ = 0;
  uint64_t rejected_payloads_ = 0;
  cs30::StartupCollector collector_;
  std::unique_ptr<UvcFrameAssembler> assembler_;
  std::vector<std::string> enumerated_ids_;
  SensorAdapter::EventCallback callback_;
  std::string device_id_;
  bool opened_ = false;
  bool active_ = false;
  bool accepting_ = false;
  bool notified_ = false;
  uint64_t session_ = 0;
  uint64_t next_frame_id_ = 1;
  uint64_t transfers_ = 0;
  CameraStatus terminal_;
  CameraStreamProfile profile_;
  CameraCaptureSettings settings_;
  std::shared_ptr<const CameraCalibration> calibration_;
  std::shared_ptr<const FrameBundle> latest_;
};

}  // namespace lingtouch
