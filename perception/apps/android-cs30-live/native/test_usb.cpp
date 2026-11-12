// Test-only libusb boundary. Includes the REAL vendored public ABI header.
// The production Android JNI target links real libusb, never this file.
#include <libusb.h>
#include "fake_usb.h"
#include <algorithm>
#include <chrono>
#include <cstdlib>
#include <cstring>
#include <deque>
#include <mutex>
#include <thread>
#include <unordered_map>
#include <set>
#include "test_usb_controls.h"
#include "lingtouch/report_json.h"
struct libusb_context {};
struct libusb_device_handle {};
struct libusb_device {};
namespace {
std::mutex mutex_;
std::vector<uint8_t> calibration;
std::string startup_fault;
std::deque<mock_usb::Packet> packets;
std::deque<libusb_transfer*> pending;
std::unordered_map<libusb_transfer*, bool> cancelled;
std::vector<std::string> trace;
size_t slice_index[2]{};
int allocated=0,contexts=0,handles=0,claims=0,initial_submits=0,callbacks=0;
bool unplugged=false,queue_logged=false;
std::set<int> java_claims;
std::unordered_map<libusb_device_handle*,std::set<int>> native_claims;
std::unordered_map<libusb_device_handle*,bool> auto_detach;
std::unordered_map<libusb_transfer*,std::chrono::steady_clock::time_point> cancel_after;
libusb_transfer* executing_callback=nullptr;
int unsafe_frees=0,unsafe_closes=0,auto_enables=0,force_calls=0,release_failures=0;
int startup_attempts=0,device_resets=0,stream_alt=0;
int control_alt_calls=0,stop_alt_after_timeout=0;
int iso_allocation_failures=0;
bool stream_alt_timed_out=false;
bool stream_idle_before_commit=false;
std::string bytes_json(const unsigned char* data, size_t n) {
  std::string s="[";
  for(size_t i=0;i<n;++i){if(i)s+=",";s+=std::to_string(data[i]);}
  return s+"]";
}
}
namespace mock_usb {
void configure(std::vector<uint8_t> blob, std::string fault) {
  std::lock_guard<std::mutex> lock(mutex_);
  calibration=std::move(blob); startup_fault=std::move(fault);
  packets.clear(); pending.clear(); cancelled.clear(); trace.clear();
  slice_index[0]=slice_index[1]=0;
  allocated=contexts=handles=claims=initial_submits=callbacks=0;
  unplugged=queue_logged=false;
  java_claims.clear();native_claims.clear();auto_detach.clear();cancel_after.clear();executing_callback=nullptr;
  unsafe_frees=unsafe_closes=auto_enables=force_calls=release_failures=0;
  startup_attempts=device_resets=stream_alt=0;
  if (startup_fault == "powered_replug") stream_alt = 1;
  control_alt_calls=stop_alt_after_timeout=0;
  iso_allocation_failures=0;
  stream_alt_timed_out=false;
  stream_idle_before_commit=false;
}
void enqueue(const std::vector<uint8_t>& raw, int fid, const std::string& fault) {
  std::lock_guard<std::mutex> lock(mutex_);
  size_t offset=0,index=0;
  while(offset<raw.size()) {
    const size_t header = fault=="extended_header" ? 12 : 2;
    const size_t n=std::min<size_t>(3072-header,raw.size()-offset);
    Packet p; p.bytes.assign(header+n,0);
    p.bytes[0]=static_cast<uint8_t>(header);
    p.bytes[1]=static_cast<uint8_t>(fid | (offset+n==raw.size()&&fault!="missing_eof"?2:0));
    std::memcpy(p.bytes.data()+header,raw.data()+offset,n);
    if(index==20) {
      if(fault=="packet_error") p.status=LIBUSB_TRANSFER_ERROR;
      if(fault=="bad_header") p.bytes[0]=1;
      if(fault=="uvc_error") p.bytes[1]|=0x40;
    }
    if(!(fault=="drop_packet"&&index==20)) packets.push_back(std::move(p));
    if(fault=="duplicate_packet"&&index==30) packets.push_back(packets.back());
    if(fault=="empty_slots"&&index%3==0) packets.push_back(Packet{});
    offset+=n; ++index;
  }
}
void disconnect() { std::lock_guard<std::mutex> lock(mutex_); unplugged=true; }
bool clean() {
  std::lock_guard<std::mutex> lock(mutex_);
  return pending.empty()&&allocated==0&&contexts==0&&handles==0&&claims==0;
}
std::string report_json() {
  std::lock_guard<std::mutex> lock(mutex_);
  std::string s="{\"trace\":[";
  for(size_t i=0;i<trace.size();++i){if(i)s+=",";s+=trace[i];}
  s+="],\"callbacks\":"+std::to_string(callbacks)+",\"initial_submits\":"+std::to_string(initial_submits);
  s+=",\"allocated_remaining\":"+std::to_string(allocated)+",\"pending_remaining\":"+std::to_string(pending.size());
  return s+",\"claimed_remaining\":"+std::to_string(claims)+"}";
}
}
bool mock_java_claim(int id,bool force) {
  std::lock_guard<std::mutex> lock(mutex_);
  if(id<0||id>255)return false;
  if(force)++force_calls;
  if(startup_fault=="java_claim_fail"&&id==1)return false;
  java_claims.insert(id);return true;
}
bool mock_java_release(int id) {std::lock_guard<std::mutex> lock(mutex_);return java_claims.erase(id)>0;}
std::string mock_policy_report() {
  std::lock_guard<std::mutex> lock(mutex_);
  return "{\"auto_detach_enables\":"+std::to_string(auto_enables)+",\"java_force_calls\":"+std::to_string(force_calls)+
    ",\"unsafe_frees\":"+std::to_string(unsafe_frees)+",\"unsafe_closes\":"+std::to_string(unsafe_closes)+
    ",\"contexts\":"+std::to_string(contexts)+",\"handles\":"+std::to_string(handles)+
    ",\"pending\":"+std::to_string(pending.size())+",\"allocated\":"+std::to_string(allocated)+
    ",\"native_claims\":"+std::to_string(claims)+",\"callbacks\":"+std::to_string(callbacks)+
    ",\"device_resets\":"+std::to_string(device_resets)+",\"control_alt_calls\":"+std::to_string(control_alt_calls)+
    ",\"stop_alt_after_timeout\":"+std::to_string(stop_alt_after_timeout)+
    ",\"iso_allocation_failures\":"+std::to_string(iso_allocation_failures)+"}";
}
extern "C" {
libusb_device* LIBUSB_CALL libusb_get_device(libusb_device_handle*) {static libusb_device device;return &device;}
int LIBUSB_CALL libusb_get_device_speed(libusb_device*) {return LIBUSB_SPEED_HIGH;}
int LIBUSB_CALL libusb_get_configuration(libusb_device_handle*,int* configuration){*configuration=1;return 0;}
int LIBUSB_CALL libusb_get_active_config_descriptor(libusb_device*, libusb_config_descriptor** out) {
  static const auto control = [] {
    libusb_interface_descriptor descriptor{};
    descriptor.bInterfaceNumber = 0;
    return descriptor;
  }();
  static const libusb_interface_descriptor streaming[] = {[] {
    libusb_interface_descriptor descriptor{};
    descriptor.bInterfaceNumber = 1;
    return descriptor;
  }(), [] {
    libusb_interface_descriptor descriptor{};
    descriptor.bInterfaceNumber = 1;
    descriptor.bAlternateSetting = 1;
    return descriptor;
  }()};
  static const libusb_interface interfaces[] = {{&control, 1}, {streaming, 2}};
  static auto config = [] {
    libusb_config_descriptor descriptor{};
    descriptor.bNumInterfaces = 2;
    descriptor.bConfigurationValue = 1;
    descriptor.interface = interfaces;
    return descriptor;
  }();
  *out = &config;
  return 0;
}
void LIBUSB_CALL libusb_free_config_descriptor(libusb_config_descriptor*) {}
int LIBUSB_CALL libusb_init_context(libusb_context** ctx, const libusb_init_option*, int) {
  std::lock_guard<std::mutex> lock(mutex_); *ctx=new libusb_context; ++contexts; return 0;
}
void LIBUSB_CALL libusb_exit(libusb_context* ctx) {
  std::lock_guard<std::mutex> lock(mutex_); delete ctx; --contexts;
}
int LIBUSB_CALL libusb_wrap_sys_device(libusb_context*, intptr_t fd, libusb_device_handle** handle) {
  if(fd<0) return LIBUSB_ERROR_ACCESS;
  std::lock_guard<std::mutex> lock(mutex_); *handle=new libusb_device_handle; ++handles; return 0;
}
libusb_device_handle* LIBUSB_CALL libusb_open_device_with_vid_pid(libusb_context* c, uint16_t vid, uint16_t pid) {
  libusb_device_handle* h=nullptr;
  if(vid==0x2207&&pid==0x0016) libusb_wrap_sys_device(c,42,&h);
  return h;
}
void LIBUSB_CALL libusb_close(libusb_device_handle* h) {
  std::lock_guard<std::mutex> lock(mutex_);
  if(!pending.empty()||executing_callback)++unsafe_closes;
  native_claims.erase(h);auto_detach.erase(h);delete h; --handles;
}
const char* LIBUSB_CALL libusb_error_name(int code) { return code==LIBUSB_ERROR_TIMEOUT?"MOCK_TIMEOUT":"MOCK_USB_ERROR"; }
int LIBUSB_CALL libusb_set_auto_detach_kernel_driver(libusb_device_handle* h,int enable) {
  std::lock_guard<std::mutex> lock(mutex_);auto_detach[h]=enable!=0;if(enable)++auto_enables;return 0;
}
int LIBUSB_CALL libusb_kernel_driver_active(libusb_device_handle*,int) {return 0;}
int LIBUSB_CALL libusb_claim_interface(libusb_device_handle* h,int id) {
  std::lock_guard<std::mutex> lock(mutex_);
  if(id<0||id>255)return LIBUSB_ERROR_INVALID_PARAM;
  // Faithful ownership regression: EXCEPT_DRIVER usbfs rejects even this fd's
  // Java preclaim; raw CLAIMINTERFACE on the shared open-file description succeeds.
  if(auto_detach[h]&&java_claims.count(id))return LIBUSB_ERROR_BUSY;
  if(!java_claims.count(id))return LIBUSB_ERROR_BUSY;
  if(native_claims[h].insert(id).second)++claims;
  return 0;
}
int LIBUSB_CALL libusb_release_interface(libusb_device_handle* h,int id) {
  std::lock_guard<std::mutex> lock(mutex_);
  if(startup_fault=="release_fail_once"&&release_failures++==0)return LIBUSB_ERROR_BUSY;
  if(native_claims[h].erase(id)){--claims;java_claims.erase(id);return 0;}
  return LIBUSB_ERROR_NOT_FOUND;
}
int LIBUSB_CALL libusb_set_interface_alt_setting(libusb_device_handle*,int interface_number,int alt) {
  std::lock_guard<std::mutex> lock(mutex_);
  if (interface_number == 0) {
    ++control_alt_calls;
    if (startup_fault == "fixed_control_alt_other") return LIBUSB_ERROR_OTHER;
  }
  if (interface_number == 1 && alt == 1 && device_resets == 0 &&
      (startup_fault == "stream_alt_timeout" || startup_fault == "stream_alt_reset_not_found" ||
       (startup_fault == "powered_replug" && !stream_idle_before_commit))) {
    stream_alt_timed_out = true;
    return LIBUSB_ERROR_OTHER;
  }
  if (interface_number == 1 && alt == 0 && stream_alt_timed_out) {
    ++stop_alt_after_timeout;
    return LIBUSB_ERROR_OTHER;
  }
  if(interface_number==1)stream_alt=alt;
  trace.push_back("{\"kind\":\"alt\",\"interface\":"+std::to_string(interface_number)+",\"alt\":"+std::to_string(alt)+"}");
  return 0;
}
int LIBUSB_CALL libusb_reset_device(libusb_device_handle*) {
  std::lock_guard<std::mutex> lock(mutex_);
  // A device reset is safe only after cancellation callbacks and release.
  if(!pending.empty()||executing_callback||allocated||claims||stream_alt!=0)return LIBUSB_ERROR_BUSY;
  ++device_resets;
  stream_alt_timed_out=false;
  if (startup_fault == "stream_alt_reset_not_found") return LIBUSB_ERROR_NOT_FOUND;
  return 0;
}
int LIBUSB_CALL libusb_control_transfer(libusb_device_handle*,uint8_t type,uint8_t request,uint16_t value,
                                      uint16_t index,unsigned char* data,uint16_t length,unsigned int timeout) {
  std::lock_guard<std::mutex> lock(mutex_);
  unsigned char setup[8]={type,request,static_cast<uint8_t>(value),static_cast<uint8_t>(value>>8),
    static_cast<uint8_t>(index),static_cast<uint8_t>(index>>8),static_cast<uint8_t>(length),static_cast<uint8_t>(length>>8)};
  trace.push_back("{\"kind\":\"control\",\"setup\":"+bytes_json(setup,8)+",\"data\":"+
    ((type&0x80)?"[]":bytes_json(data,length))+",\"timeout_ms\":"+std::to_string(timeout)+"}");
  if(startup_fault=="startup_timeout"&&value==0x0200) return LIBUSB_ERROR_TIMEOUT;
  if (value == 0x0200 && startup_fault == "powered_replug") {
    stream_idle_before_commit = stream_alt == 0;
  }
  if(value==0xcb00){
    ++startup_attempts;
    slice_index[0]=slice_index[1]=0;
    initial_submits=0;
    queue_logged=false;
  }
  if(!(type&0x80)) {
    if((value==0xa600||value==0xa700||value==0xa300)&&cancelled.size()!=10) return LIBUSB_ERROR_IO;
    return length;
  }
  std::memset(data,0,length);
  if(value==0xc100||value==0xc200) {
    const auto offset=55*slice_index[value==0xc200]++;
    const auto n=std::min<size_t>(55,calibration.size()-offset),end=offset+n;
    if(startup_fault=="calibration_truncated"&&offset==55) return 3;
    if(length<5+n) return LIBUSB_ERROR_OVERFLOW;
    data[0]=static_cast<uint8_t>(calibration.size()); data[1]=static_cast<uint8_t>(calibration.size()>>8);
    data[2]=static_cast<uint8_t>(end);data[3]=static_cast<uint8_t>(end>>8);data[4]=static_cast<uint8_t>(n);
    std::memcpy(data+5,calibration.data()+offset,n);
  } else if(value==0xc800) {
    const char serial[]="SIM-HV0130315L0294";
    std::memcpy(data,serial,std::min<size_t>(length,sizeof(serial)-1));
  } else if(value==0x0100&&length==26) {
    const unsigned char probe[26]={1,0,1,1,0x80,0xf0,0xfa,2,0,0,0,0,0,0,0,0,0,0,0,0x60,9,0,0,4,0,0};
    std::memcpy(data,probe,26);
  }
  return length;
}
libusb_transfer* LIBUSB_CALL libusb_alloc_transfer(int packets_count) {
  auto* t=static_cast<libusb_transfer*>(std::calloc(1,sizeof(libusb_transfer)+packets_count*sizeof(libusb_iso_packet_descriptor)));
  std::lock_guard<std::mutex> lock(mutex_); if(t)++allocated; return t;
}
void LIBUSB_CALL libusb_free_transfer(libusb_transfer* t) {
  std::lock_guard<std::mutex> lock(mutex_);
  if(std::find(pending.begin(),pending.end(),t)!=pending.end()||executing_callback==t)++unsafe_frees;
  cancelled.erase(t);
  cancel_after.erase(t);
  std::free(t); --allocated;
}
int LIBUSB_CALL libusb_submit_transfer(libusb_transfer* t) {
  std::lock_guard<std::mutex> lock(mutex_);
  if(unplugged)return LIBUSB_ERROR_NO_DEVICE;
  if (startup_fault == "iso_memory_exhausted" ||
      (t->num_iso_packets > 4 && (startup_fault == "iso_memory_first_slot" ||
          (startup_fault == "iso_memory_partial_queue" && pending.size() >= 3)))) {
    ++iso_allocation_failures;
    return LIBUSB_ERROR_NO_MEM;
  }
  if(startup_fault=="resubmit_fail"&&cancelled.count(t))return LIBUSB_ERROR_IO;
  if(startup_fault=="submit_fail"&&initial_submits==3&&!cancelled.count(t))return LIBUSB_ERROR_IO;
  if(startup_fault=="reconnect_submit_io"&&startup_attempts>=2&&device_resets==0&&
      initial_submits==3&&!cancelled.count(t))return LIBUSB_ERROR_IO;
  if(std::find(pending.begin(),pending.end(),t)!=pending.end())return LIBUSB_ERROR_BUSY;
  if(!cancelled.count(t)) {
    ++initial_submits;
    if(!queue_logged) {
      trace.push_back("{\"kind\":\"queue_iso\",\"endpoint\":"+std::to_string(t->endpoint)+
        ",\"transfers\":10,\"bytes\":"+std::to_string(t->length)+",\"packets\":"+std::to_string(t->num_iso_packets)+"}");
      queue_logged=true;
    }
  }
  cancelled[t]=false; pending.push_back(t); return 0;
}
int LIBUSB_CALL libusb_cancel_transfer(libusb_transfer* t) {
  std::lock_guard<std::mutex> lock(mutex_);
  if(std::find(pending.begin(),pending.end(),t)==pending.end())return LIBUSB_ERROR_NOT_FOUND;
  cancelled[t]=true; return 0;
}
void LIBUSB_CALL libusb_interrupt_event_handler(libusb_context*) {}
int LIBUSB_CALL libusb_handle_events_timeout_completed(libusb_context*,timeval*,int*) {
  libusb_transfer* t=nullptr;
  {
    std::lock_guard<std::mutex> lock(mutex_);
    const auto now=std::chrono::steady_clock::now();
    auto it=std::find_if(pending.begin(),pending.end(),[&](auto* q){
      if(cancelled[q]&&startup_fault=="delay_cancel") {
        if(!cancel_after.count(q))cancel_after[q]=now+std::chrono::milliseconds(3600);
        return now>=cancel_after[q];
      }
      return cancelled[q]||unplugged||!packets.empty()||startup_fault=="resubmit_fail"||(startup_fault=="fast_completion"&&callbacks<10000);
    });
    if(it!=pending.end()) {
      t=*it; pending.erase(it); ++callbacks;
      t->status=cancelled[t]?LIBUSB_TRANSFER_CANCELLED:(unplugged?LIBUSB_TRANSFER_NO_DEVICE:LIBUSB_TRANSFER_COMPLETED);
      if(t->status==LIBUSB_TRANSFER_COMPLETED) {
        std::memset(t->buffer,0xEE,t->length);
        size_t offset=0;
        for(int i=0;i<t->num_iso_packets;++i) {
          auto& d=t->iso_packet_desc[i]; d.actual_length=0;d.status=LIBUSB_TRANSFER_COMPLETED;
          if(!packets.empty()) {
            auto p=std::move(packets.front());packets.pop_front();
            d.actual_length=static_cast<unsigned int>(p.bytes.size());d.status=static_cast<libusb_transfer_status>(p.status);
            if(!p.bytes.empty())std::memcpy(t->buffer+offset,p.bytes.data(),p.bytes.size());
          }
          offset+=d.length;
        }
      }
    }
  }
  if(t){
    {std::lock_guard<std::mutex> lock(mutex_);executing_callback=t;}
    t->callback(t);
    {std::lock_guard<std::mutex> lock(mutex_);executing_callback=nullptr;}
  }
  else std::this_thread::sleep_for(std::chrono::milliseconds(1));
  return 0;
}
}
