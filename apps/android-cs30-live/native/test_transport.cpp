#include "test_usb_controls.h"
#include "fake_usb.h"
#include "lingtouch/config.h"
#include "lingtouch/engine.h"
#include "lingtouch/perception/cs30_libusb_source.h"
#include <libusb.h>
#include <stdexcept>
#include <vector>
using namespace lingtouch;
namespace {
void require(bool condition,const char* text){if(!condition)throw std::runtime_error(text);}
}
std::string run_transport_regressions(const unsigned char* blob,size_t size){
  const std::vector<uint8_t> bytes(blob,blob+size);
  std::string out="{\"passed\":true,\"checks\":[";
  auto record=[&](const std::string& text){if(out.back()!='[')out+=",";out+="\""+text+"\"";};
  mock_usb::configure(bytes,"");
  require(mock_java_claim(0,true),"Java preclaim setup");
  libusb_context* ctx=nullptr;require(libusb_init_context(&ctx,nullptr,0)==0,"Init");
  libusb_device_handle* h=nullptr;require(libusb_wrap_sys_device(ctx,42,&h)==0,"Wrap");
  require(libusb_set_auto_detach_kernel_driver(h,1)==0,"Enable");
  require(libusb_claim_interface(h,0)==LIBUSB_ERROR_BUSY,"Must reproduce EXCEPT_DRIVER usbfs BUSY");
  require(libusb_set_auto_detach_kernel_driver(h,0)==0&&libusb_claim_interface(h,0)==0,"Same-fd raw claim must succeed");
  require(libusb_release_interface(h,0)==0,"Release");libusb_close(h);libusb_exit(ctx);
  require(mock_usb::clean(),"Ownership test leaked resources");
  record("Reproduced Java-preclaimed usbfs BUSY with auto-detach, then succeeded with auto-detach disabled");
  require(!Cs30LibusbSource::supports_interface(-1)&&!Cs30LibusbSource::supports_interface(2)&&
      !Cs30LibusbSource::supports_interface(255)&&Cs30LibusbSource::supports_interface(0)&&Cs30LibusbSource::supports_interface(1),"Interface bounds");
  record("Invalid interface numbers are rejected before array access");
  std::string retained;
  for(const auto& fault:std::vector<std::string>{"fast_completion","submit_fail","resubmit_fail","delay_cancel","release_fail_once"}){
    mock_usb::configure(bytes,fault);require(mock_java_claim(0,true)&&mock_java_claim(1,true),"Java force setup");
    Engine engine(default_config().value());
    auto opened=Cs30LibusbSource::open_fd(42,&engine,[](const std::string&){});require(static_cast<bool>(opened),"Open source");
    auto source=std::move(opened.value());const auto started=source->start();
    if(fault=="submit_fail"||fault=="resubmit_fail")require(!started,"Failed transfer queue must not report successful startup");
    else require(static_cast<bool>(started),"Startup should succeed");
    const auto stopped=source->stop();
    if(fault=="delay_cancel"){
      require(!stopped,"Cancellation timeout should preserve ownership");retained=mock_policy_report();
      require(retained.find("\"allocated\":10")!=std::string::npos&&retained.find("\"native_claims\":2")!=std::string::npos&&
              retained.find("\"handles\":1")!=std::string::npos&&retained.find("\"contexts\":1")!=std::string::npos,"Timed-out cleanup freed resources early");
      require(static_cast<bool>(source->stop()),"Late callbacks should drain on retry");
      record("Cancellation timeout preserves all transfers, claims, handle, context and event pump until late callbacks complete");
    } else if(fault=="release_fail_once"){
      require(!stopped&&mock_policy_report().find("\"native_claims\":1")!=std::string::npos,"Failed release lost claimed state");
      require(!source->start(),"Reopen must refuse an unreleased interface");
      require(static_cast<bool>(source->stop()),"Release retry must succeed");
      record("Failed release preserves its claim and a later retry releases it");
    } else {
      require(static_cast<bool>(stopped),"Stop should drain");
      record(fault=="fast_completion"?"Rapid callback and resubmission stress drains safely":
          fault=="resubmit_fail"?"Exhausted transfer queue cannot report a successful connection":
          "Partial initial submission rolls back its pending reservation and drains earlier transfers");
    }
    source.reset();require(mock_usb::clean(),"Resource leak after cleanup");
    const auto policy=mock_policy_report();
    require(policy.find("\"unsafe_frees\":0")!=std::string::npos&&policy.find("\"unsafe_closes\":0")!=std::string::npos&&
            policy.find("\"auto_detach_enables\":0")!=std::string::npos,"Unsafe ownership operation detected");
  }
  out+="],\"timeout_retained\":"+retained+",\"final_policy\":"+mock_policy_report()+"}";
  return out;
}
