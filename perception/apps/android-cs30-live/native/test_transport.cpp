#include "test_usb_controls.h"
#include "fake_usb.h"
#include "lingtouch/config.h"
#include "lingtouch/engine.h"
#include "lingtouch/perception/cs30_libusb_source.h"
#include <libusb.h>
#include <chrono>
#include <stdexcept>
#include <thread>
#include <vector>
using namespace lingtouch;
using Recovery = Cs30LibusbSource::Recovery;
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
    if(fault!="submit_fail")require(source->reset_after_startup_error()==Recovery::Unavailable,"Reset attempted for an unrelated error");
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
  {
    mock_usb::configure(bytes,"reconnect_submit_io");
    Engine engine(default_config().value());
    auto open=[&](int fd) {
      require(mock_java_claim(0,true)&&mock_java_claim(1,true),"Each fresh connection must preclaim");
      auto result=Cs30LibusbSource::open_fd(fd,&engine,[](const std::string&){});
      require(static_cast<bool>(result),"Open fresh platform fd");
      return std::move(result.value());
    };
    auto first=open(42);
    require(static_cast<bool>(first->start()),"First connection should start");
    require(static_cast<bool>(first->stop()),"First connection should stop");
    first.reset();
    require(mock_usb::clean(),"First connection leaked resources");

    auto failed=open(43);
    const auto started=failed->start();
    require(!started&&started.message.find("libusb_submit_transfer")!=std::string::npos,
        "Second connection must reproduce the initial ISO submit I/O error");
    require(failed->reset_after_startup_error()==Recovery::Reopen,"Reset should succeed after partial queue drains");
    require(failed->reset_after_startup_error()==Recovery::Unavailable,"Recovery must consume the startup error once");
    failed.reset();
    require(mock_usb::clean(),"Failed connection leaked resources before retry");

    auto retried=open(44);
    require(static_cast<bool>(retried->start()),"Fresh claims and full startup must recover the connection");
    require(static_cast<bool>(retried->stop()),"Recovered connection should stop");
    retried.reset();
    require(mock_usb::clean(),"Recovered connection leaked resources");
    const auto policy=mock_policy_report();
    require(policy.find("\"unsafe_frees\":0")!=std::string::npos&&
            policy.find("\"unsafe_closes\":0")!=std::string::npos,"Unsafe recovery cleanup");
    record("Reconnect ISO submit I/O drains partial transfers, resets once, and reopens with fresh claims");
  }
  for (const auto& fault : std::vector<std::string>{"fixed_control_alt_other", "stream_alt_timeout"}) {
    mock_usb::configure(bytes, fault);
    Engine engine(default_config().value());
    auto open=[&](int fd) {
      require(mock_java_claim(0,true)&&mock_java_claim(1,true),"Alt test preclaim");
      auto result=Cs30LibusbSource::open_fd(fd,&engine,[](const std::string&){});
      require(static_cast<bool>(result),"Open alt test connection");
      return std::move(result.value());
    };
    auto source = open(42);
    const auto started = source->start();
    if (fault == "fixed_control_alt_other") {
      require(static_cast<bool>(started),"Single-alt control interface should start without SET_INTERFACE");
      require(source->reset_after_startup_error()==Recovery::Unavailable,"Control interface should not require recovery");
    } else {
      require(!started && started.message.find("set interface 1 alt 1") != std::string::npos,
          "Mandatory streaming alt failure must block startup and identify the interface");
      require(mock_usb::report_json().find("\"initial_submits\":0") != std::string::npos,
          "Never submit ISO requests before the stream alt is enabled");
      require(mock_policy_report().find("\"stop_alt_after_timeout\":0") != std::string::npos,
          "Cleanup must not issue a second SET_INTERFACE to the timed-out stream");
      require(source->reset_after_startup_error()==Recovery::Reopen,"Streaming alt failure should permit a safe reset");
      require(source->reset_after_startup_error()==Recovery::Unavailable,"Streaming alt failure should permit only one reset");
      source.reset();
      require(mock_usb::clean(),"Timed-out session leaked resources");
      source = open(43);
      require(static_cast<bool>(source->start()),"Streaming alt should succeed on fresh connection after reset");
    }
    require(static_cast<bool>(source->stop()),"Alt test should stop");
    source.reset();
    require(mock_usb::clean(),"Alt test leaked resources");
    require(mock_policy_report().find("\"control_alt_calls\":0") != std::string::npos,
        "Fixed control alt must not be set during startup or shutdown");
    record(fault == "fixed_control_alt_other" ?
        "Single-alt control interface skips redundant SET_INTERFACE on start and stop" :
        "Streaming alt timeout blocks ISO submission, releases claims and resets once before reopening");
  }
  for (const auto& fault : std::vector<std::string>{
           "iso_memory_first_slot", "iso_memory_partial_queue", "iso_memory_exhausted"}) {
    mock_usb::configure(bytes, fault);
    require(mock_java_claim(0, true) && mock_java_claim(1, true), "ISO memory test preclaim");
    Engine engine(default_config().value(), true);
    auto opened = Cs30LibusbSource::open_fd(42, &engine, [](const std::string&) {});
    require(static_cast<bool>(opened), "Open ISO memory test connection");
    auto source = std::move(opened.value());
    const auto started = source->start();
    if (fault == "iso_memory_exhausted") {
      require(!started, "Startup must fail if every smaller queue is rejected");
      require(source->reset_after_startup_error()==Recovery::Unavailable, "Memory exhaustion must not reset the device");
      require(mock_policy_report().find("\"iso_allocation_failures\":3") != std::string::npos,
          "Memory fallback must stop after 8, 4 and 2 packets per transfer");
      record("Persistent ISO allocation failure stops after bounded retries without resetting");
    } else {
      require(static_cast<bool>(started), "Smaller isochronous queue should recover allocation failure");
      require(mock_policy_report().find("\"iso_allocation_failures\":1") != std::string::npos,
          "Expected one rejected large request before retry");
      require(engine.intrinsics().has_value(), "Same-session retry must preserve camera calibration");
      mock_usb::enqueue(std::vector<uint8_t>(cs30::kFrameBytes, 0), 0);
      const auto deadline = std::chrono::steady_clock::now() + std::chrono::seconds(2);
      while (engine.stats().assembler.frames == 0 && std::chrono::steady_clock::now() < deadline) {
        std::this_thread::sleep_for(std::chrono::milliseconds(5));
      }
      require(engine.stats().assembler.frames == 1, "Smaller requests must still assemble a full depth frame");
      record(fault == "iso_memory_first_slot" ?
          "First-slot ENOMEM falls back in the same session and assembles a complete depth frame" :
          "Partial-queue ENOMEM drains accepted transfers before retrying smaller requests");
    }
    require(static_cast<bool>(source->stop()), "Stop ISO memory test");
    source.reset();
    require(mock_usb::clean(), "ISO memory fallback leaked resources");
    const auto policy = mock_policy_report();
    require(policy.find("\"device_resets\":0") != std::string::npos &&
            policy.find("\"unsafe_frees\":0") != std::string::npos &&
            policy.find("\"unsafe_closes\":0") != std::string::npos, "Unsafe ISO memory recovery");
  }
  for (const auto& fault : std::vector<std::string>{"powered_replug", "stream_alt_reset_not_found"}) {
    mock_usb::configure(bytes, fault);
    require(mock_java_claim(0, true) && mock_java_claim(1, true), "Replug test preclaim");
    Engine engine(default_config().value(), true);
    auto opened = Cs30LibusbSource::open_fd(42, &engine, [](const std::string&) {});
    require(static_cast<bool>(opened), "Open replug test connection");
    auto source = std::move(opened.value());
    if (fault == "powered_replug") {
      require(static_cast<bool>(source->start(true)), "Powered replug must restore stream alt 0 before Commit");
      require(mock_policy_report().find("\"device_resets\":0") != std::string::npos,
          "Restoring stream idle should avoid a bus reset");
      record("Powered replug restores stream alt 0 before UVC Commit");
    } else {
      require(!source->start(), "Simulated alt selection timeout");
      require(source->reset_after_startup_error() == Recovery::Rediscover,
          "Reset NOT_FOUND must invalidate the old fd and require rediscovery");
      require(source->reset_after_startup_error() == Recovery::Unavailable,
          "Never reset the missing device again");
      record("Reset NOT_FOUND closes the old session and requires rediscovery");
    }
    require(static_cast<bool>(source->stop()), "Stop replug test");
    source.reset();
    require(mock_usb::clean(), "Replug test leaked USB resources");
  }
  out+="],\"timeout_retained\":"+retained+",\"final_policy\":"+mock_policy_report()+"}";
  return out;
}
