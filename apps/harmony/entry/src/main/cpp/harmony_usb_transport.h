#pragma once
#include "lingtouch/perception/cs30_capture.h"
#include <atomic>
#include <array>
#include <optional>

namespace lingtouch {
enum class HarmonyUsbOperation { kEnumerate, kOpen, kClaim, kSetAlt, kControl, kStartIso, kStopIso, kClose };
struct HarmonyUsbCommand {
  uint64_t request_id=0;
  uint64_t epoch=0;
  HarmonyUsbOperation operation=HarmonyUsbOperation::kEnumerate;
  std::string device_id;
  int interface_number=0;
  int alternate=0;
  CameraUsbControl control;
  CameraIsoConfig iso;
};
struct HarmonyUsbReply {
  std::vector<CameraUsbDevice> devices;
  std::vector<uint8_t> data;
};
// execute() is called only on a native worker; dispatch runs on ArkTS through a
// Node-API threadsafe function. complete()/push_packets() run on the ArkTS loop.
class HarmonyUsbBridge {
 public:
  using Dispatcher=std::function<bool(const HarmonyUsbCommand&)>;
  HarmonyUsbBridge();
  ~HarmonyUsbBridge();
  void set_dispatcher(Dispatcher dispatcher);
  CameraStatus execute(HarmonyUsbCommand command,HarmonyUsbReply& reply);
  void complete(uint64_t request_id,CameraStatus status,HarmonyUsbReply reply);
  void abort();
  void set_sinks(uint64_t epoch,CameraUsbTransport::PacketSink packets,CameraUsbTransport::EventSink events,
                 size_t transfer_bytes=128*3072);
  void push_packets(uint64_t epoch,const uint8_t*,size_t,const IsoPacketDesc*,size_t);
  void push_event(uint64_t epoch,const CameraStatus&);
  std::string receive_diagnostics() const;
 private:
  std::mutex mutex_;
  std::condition_variable ready_;
  Dispatcher dispatcher_;
  uint64_t next_id_=1;
  uint64_t waiting_id_=0;
  bool done_=false;
  bool aborted_=false;
  CameraStatus result_;
  HarmonyUsbReply reply_;
  std::mutex delivery_;
  uint64_t epoch_=0;
  CameraUsbTransport::PacketSink packets_;
  CameraUsbTransport::EventSink events_;
  // The ArkTS callback copies one small transfer, never assembles a full frame.
  // A fixed pool bounds memory and preserves receive order on one worker.
  static constexpr size_t kQueueCapacity=32;
  struct Batch {
    std::vector<uint8_t> bytes;
    std::array<IsoPacketDesc,128> descs{};
    size_t size=0,count=0;
  };
  std::array<Batch,kQueueCapacity> queue_;
  mutable std::mutex queue_mutex_;
  std::condition_variable queued_;
  std::thread receiver_;
  size_t head_=0,queued_count_=0,high_water_=0,transfer_bytes_=0;
  uint64_t queued_epoch_=0,overflows_=0;
  bool accepting_=false,shutting_down_=false;
  std::optional<CameraStatus> queued_event_;
  void receive_loop();
};
class HarmonyUsbTransport final : public CameraUsbTransport {
 public:
  explicit HarmonyUsbTransport(std::shared_ptr<HarmonyUsbBridge> bridge):bridge_(std::move(bridge)){}
  ~HarmonyUsbTransport() override;
  CameraStatus enumerate(std::vector<CameraUsbDevice>&) override;
  CameraStatus open(const std::string&) override;
  CameraStatus claim(int) override;
  CameraStatus set_alt(int,int) override;
  CameraStatus control(const CameraUsbControl&,std::vector<uint8_t>&) override;
  CameraStatus start_iso(const CameraIsoConfig&,PacketSink,EventSink) override;
  CameraStatus stop_iso() override;
  CameraStatus close() override;
 private:
  CameraStatus run(HarmonyUsbCommand command);
  std::shared_ptr<HarmonyUsbBridge> bridge_;
  bool opened_=false;
  bool streaming_=false;
  uint64_t epoch_=0;
};
} // namespace lingtouch
