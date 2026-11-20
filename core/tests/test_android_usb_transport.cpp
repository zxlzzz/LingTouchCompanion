// Fault-injection tests for the real Android transport. Only the OS/libusb
// boundary is simulated; request submission, callback draining and fd ownership
// use the production implementation. This does not validate an Android driver.
#include "../../apps/android/app/src/main/cpp/android_usb_transport.h"
#include "test_harness.h"
#include <libusb.h>
#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <deque>
#include <future>
#include <set>

struct libusb_context {};
struct libusb_device {};
struct libusb_device_handle {};
namespace {
using namespace lingtouch;
using namespace std::chrono_literals;
struct MockUsb {
  std::mutex mutex;
  std::condition_variable cv;
  std::set<libusb_transfer*> submitted,callbacks;
  std::deque<libusb_transfer*> ready;
  bool interrupted=false,fd_open=false,device_open=false;
  int submit_calls=0,fail_submit=0,allocations=0,frees=0,control_error=0;
  int submit_error=LIBUSB_ERROR_IO,max_bytes=400000;
  std::vector<int> submitted_packets;
  int speed=LIBUSB_SPEED_HIGH;
  void reset() {
    std::lock_guard<std::mutex> lock(mutex);
    LT_CHECK(submitted.empty() && callbacks.empty() && ready.empty());
    interrupted=false;fd_open=false;device_open=false;
    submit_calls=fail_submit=allocations=frees=control_error=0;speed=LIBUSB_SPEED_HIGH;
    submit_error=LIBUSB_ERROR_IO;max_bytes=400000;submitted_packets.clear();
  }
  void complete_one(bool bad_packet=false,bool bad_count=false) {
    std::lock_guard<std::mutex> lock(mutex);
    if(submitted.empty()){LT_CHECK(false);return;}
    auto* t=*submitted.begin();t->status=LIBUSB_TRANSFER_COMPLETED;
    if(bad_packet)t->iso_packet_desc[0].actual_length=0xffffffffu;
    if(bad_count)++t->num_iso_packets;
    ready.push_back(t);cv.notify_all();
  }
} mock;
libusb_context context;
libusb_device device;
libusb_device_handle handle;
AndroidUsbHost host() {
  AndroidUsbHost h;
  h.enumerate=[](auto& out){out={{"test",true}};return CameraStatus{};};
  h.open_fd=[](const std::string&,int& fd){mock.fd_open=true;fd=7;return CameraStatus{};};
  h.close_fd=[]{
    std::lock_guard<std::mutex> lock(mock.mutex);
    LT_CHECK(mock.submitted.empty() && mock.callbacks.empty() && !mock.device_open);
    mock.fd_open=false;
  };
  return h;
}
CameraIsoConfig config(){CameraIsoConfig c;c.transfers=4;c.packets=2;return c;}
}

extern "C" {
int LIBUSB_CALL libusb_init_context(libusb_context** ctx,const libusb_init_option options[],int count) {
  LT_CHECK(count==1 && options[0].option==LIBUSB_OPTION_NO_DEVICE_DISCOVERY);
  *ctx=&context;return 0;
}
int LIBUSB_CALL libusb_wrap_sys_device(libusb_context*,intptr_t fd,libusb_device_handle** out) {
  LT_CHECK(fd==7 && mock.fd_open);*out=&handle;mock.device_open=true;return 0;
}
int LIBUSB_CALL libusb_set_auto_detach_kernel_driver(libusb_device_handle*,int enable) {
  LT_CHECK(enable==0);return 0;
}
libusb_device* LIBUSB_CALL libusb_get_device(libusb_device_handle*){return &device;}
int LIBUSB_CALL libusb_get_device_descriptor(libusb_device*,libusb_device_descriptor* d) {
  *d={};d->idVendor=cs30::kVendorId;d->idProduct=cs30::kProductId;return 0;
}
int LIBUSB_CALL libusb_get_device_speed(libusb_device*){return mock.speed;}
int LIBUSB_CALL libusb_claim_interface(libusb_device_handle*,int){return 0;}
int LIBUSB_CALL libusb_release_interface(libusb_device_handle*,int){return 0;}
int LIBUSB_CALL libusb_set_interface_alt_setting(libusb_device_handle*,int,int){return 0;}
int LIBUSB_CALL libusb_get_max_iso_packet_size(libusb_device*,unsigned char){return 3072;}
int LIBUSB_CALL libusb_control_transfer(libusb_device_handle*,uint8_t type,uint8_t,uint16_t,uint16_t,
                                       unsigned char* bytes,uint16_t length,unsigned int) {
  if(mock.control_error)return mock.control_error;
  if(type&0x80)std::fill(bytes,bytes+length,0x5a);return length;
}
libusb_transfer* LIBUSB_CALL libusb_alloc_transfer(int packets) {
  ++mock.allocations;
  return static_cast<libusb_transfer*>(std::calloc(1,sizeof(libusb_transfer)+size_t(packets)*sizeof(libusb_iso_packet_descriptor)));
}
void LIBUSB_CALL libusb_free_transfer(libusb_transfer* t) {
  std::lock_guard<std::mutex> lock(mock.mutex);
  LT_CHECK(!mock.submitted.count(t) && !mock.callbacks.count(t));++mock.frees;std::free(t);
}
int LIBUSB_CALL libusb_submit_transfer(libusb_transfer* t) {
  std::lock_guard<std::mutex> lock(mock.mutex);
  mock.submitted_packets.push_back(t->num_iso_packets);
  if(++mock.submit_calls==mock.fail_submit || t->length>mock.max_bytes)return mock.submit_error;
  LT_CHECK(!mock.submitted.count(t));mock.submitted.insert(t);return 0;
}
int LIBUSB_CALL libusb_cancel_transfer(libusb_transfer* t) {
  std::lock_guard<std::mutex> lock(mock.mutex);
  if(!mock.submitted.count(t) || std::find(mock.ready.begin(),mock.ready.end(),t)!=mock.ready.end())
    return LIBUSB_ERROR_NOT_FOUND;
  t->status=LIBUSB_TRANSFER_CANCELLED;mock.ready.push_back(t);mock.cv.notify_all();return 0;
}
int LIBUSB_CALL libusb_handle_events_timeout_completed(libusb_context*,timeval*,int*) {
  libusb_transfer* t=nullptr;
  {
    std::unique_lock<std::mutex> lock(mock.mutex);
    mock.cv.wait_for(lock,5ms,[]{return !mock.ready.empty() || mock.interrupted;});
    mock.interrupted=false;
    if(mock.ready.empty())return 0;
    t=mock.ready.front();mock.ready.pop_front();mock.submitted.erase(t);mock.callbacks.insert(t);
  }
  t->callback(t);
  {std::lock_guard<std::mutex> lock(mock.mutex);mock.callbacks.erase(t);}
  return 0;
}
void LIBUSB_CALL libusb_interrupt_event_handler(libusb_context*) {
  std::lock_guard<std::mutex> lock(mock.mutex);mock.interrupted=true;mock.cv.notify_all();
}
void LIBUSB_CALL libusb_close(libusb_device_handle*) {
  std::lock_guard<std::mutex> lock(mock.mutex);
  LT_CHECK(mock.submitted.empty() && mock.callbacks.empty());mock.device_open=false;
}
void LIBUSB_CALL libusb_exit(libusb_context*){}
const char* LIBUSB_CALL libusb_error_name(int){return "simulated USB error";}
}

LT_TEST(android_close_waits_for_callback_before_releasing_borrowed_fd) {
  mock.reset();AndroidUsbTransport usb(host());
  LT_CHECK(usb.open("test") && usb.claim(0) && usb.claim(1));
  std::promise<void> entered,release;auto started=entered.get_future(),released=release.get_future();
  LT_CHECK(usb.start_iso(config(),[&](const uint8_t*,size_t,const IsoPacketDesc*,size_t){
    entered.set_value();released.wait();
  },{}));
  mock.complete_one();LT_CHECK(started.wait_for(2s)==std::future_status::ready);
  auto closing=std::async(std::launch::async,[&]{return usb.close();});
  LT_CHECK(closing.wait_for(50ms)==std::future_status::timeout);
  LT_CHECK(mock.fd_open);release.set_value();
  LT_CHECK(closing.wait_for(2s)==std::future_status::ready);LT_CHECK(closing.get());
  LT_CHECK(!mock.fd_open && mock.allocations==mock.frees);
}
LT_TEST(android_partial_submit_failure_drains_before_smaller_queue) {
  mock.reset();mock.fail_submit=3;AndroidUsbTransport usb(host());LT_CHECK(usb.open("test"));
  LT_CHECK(usb.start_iso(config(),{},{}));
  LT_CHECK(mock.submitted.size()==4 && mock.submit_calls==7 && mock.frees==4);
  LT_CHECK(mock.fd_open);LT_CHECK(usb.close() && !mock.fd_open);
  LT_CHECK(mock.allocations==mock.frees);
}
LT_TEST(android_phone_request_sizes_are_bounded_and_other_errors_do_not_retry) {
  mock.reset();mock.max_bytes=0;AndroidUsbTransport usb(host());LT_CHECK(usb.open("test"));
  auto cfg=config();cfg.packets=32;
  LT_CHECK(!usb.start_iso(cfg,{},{}));
  LT_CHECK(mock.submitted_packets==std::vector<int>({8,4,2,1}));
  LT_CHECK(mock.submitted.empty() && mock.callbacks.empty() && mock.allocations==mock.frees);
  LT_CHECK(usb.close());
  mock.reset();mock.max_bytes=4*3072;mock.submit_error=LIBUSB_ERROR_NO_MEM;
  LT_CHECK(usb.open("test") && usb.start_iso(cfg,{},{}));
  LT_CHECK(mock.submitted_packets==std::vector<int>({8,4,4,4,4}));
  LT_CHECK(usb.close() && mock.allocations==mock.frees);
  mock.reset();mock.max_bytes=0;mock.submit_error=LIBUSB_ERROR_ACCESS;
  LT_CHECK(usb.open("test"));
  LT_CHECK(usb.start_iso(cfg,{},{}).code==CameraCode::kPermissionDenied);
  LT_CHECK(mock.submitted_packets==std::vector<int>({8}));LT_CHECK(usb.close());
}
LT_TEST(android_bad_packet_keeps_stride_and_is_marked_damaged) {
  mock.reset();AndroidUsbTransport usb(host());LT_CHECK(usb.open("test"));
  std::promise<void> checked;auto done=checked.get_future();
  LT_CHECK(usb.start_iso(config(),[&](const uint8_t*,size_t n,const IsoPacketDesc* p,size_t count){
    LT_CHECK(count==2 && n==6144 && p[0].length==3072 && p[1].length==3072);
    LT_CHECK(p[0].actual_length==0 && p[0].status!=0);checked.set_value();
  },{}));
  mock.complete_one(true);LT_CHECK(done.wait_for(2s)==std::future_status::ready);
  LT_CHECK(usb.close() && mock.allocations==mock.frees);
}
LT_TEST(android_bad_descriptor_count_is_rejected_before_array_access) {
  mock.reset();AndroidUsbTransport usb(host());LT_CHECK(usb.open("test"));
  std::promise<CameraStatus> checked;auto done=checked.get_future();
  LT_CHECK(usb.start_iso(config(),[](const uint8_t*,size_t,const IsoPacketDesc*,size_t){LT_CHECK(false);},
      [&](const CameraStatus& status){checked.set_value(status);}));
  mock.complete_one(false,true);const bool ready=done.wait_for(2s)==std::future_status::ready;
  LT_CHECK(ready);if(ready)LT_CHECK(done.get().code==CameraCode::kStreamInterrupted);
  LT_CHECK(usb.close() && mock.allocations==mock.frees);
}
LT_TEST(android_resubmit_failure_reports_error_and_can_stop) {
  mock.reset();mock.fail_submit=5;AndroidUsbTransport usb(host());LT_CHECK(usb.open("test"));
  std::promise<CameraStatus> reported;auto event=reported.get_future();
  LT_CHECK(usb.start_iso(config(),{},[&](const CameraStatus& s){reported.set_value(s);}));
  mock.complete_one();const bool ready=event.wait_for(2s)==std::future_status::ready;
  LT_CHECK(ready);if(ready)LT_CHECK(event.get().code==CameraCode::kIoError);
  LT_CHECK(usb.stop_iso() && usb.close());LT_CHECK(mock.allocations==mock.frees);
}
LT_TEST(android_control_error_keeps_output_and_known_slow_connection_closes_fd) {
  mock.reset();AndroidUsbTransport usb(host());LT_CHECK(usb.open("test"));
  CameraUsbControl request;request.request_type=0x80;request.length=4;
  std::vector<uint8_t> out{7};mock.control_error=LIBUSB_ERROR_TIMEOUT;
  LT_CHECK(!usb.control(request,out) && out==std::vector<uint8_t>{7});
  mock.control_error=0;LT_CHECK(usb.control(request,out) && out==std::vector<uint8_t>(4,0x5a));
  LT_CHECK(usb.close());mock.speed=LIBUSB_SPEED_FULL;
  LT_CHECK(!usb.open("test") && !mock.fd_open);
}
LT_TEST_MAIN()
