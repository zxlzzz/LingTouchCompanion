#pragma once
#include "lingtouch/perception/cs30_capture.h"

namespace lingtouch {
// Implemented with UsbManager in StreamService, invoked on the camera worker.
struct AndroidUsbHost {
  std::function<CameraStatus(std::vector<CameraUsbDevice>&)> enumerate;
  std::function<CameraStatus(const std::string&, int&)> open_fd;
  std::function<void()> close_fd;
  std::function<void(const std::string&)> log;
};
class AndroidUsbTransport final : public CameraUsbTransport {
 public:
  explicit AndroidUsbTransport(AndroidUsbHost host);
  ~AndroidUsbTransport() override;
  CameraStatus enumerate(std::vector<CameraUsbDevice>&) override;
  CameraStatus open(const std::string&) override;
  CameraStatus claim(int) override;
  CameraStatus set_alt(int,int) override;
  CameraStatus control(const CameraUsbControl&, std::vector<uint8_t>&) override;
  CameraStatus start_iso(const CameraIsoConfig&,PacketSink,EventSink) override;
  CameraStatus stop_iso() override;
  CameraStatus close() override;
 private:
  struct Impl;
  std::unique_ptr<Impl> impl_;
};
} // namespace lingtouch
