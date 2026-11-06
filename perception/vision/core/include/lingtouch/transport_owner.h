#pragma once
#include <atomic>
#include <chrono>
#include <thread>
#include "lingtouch/result.h"
namespace lingtouch {
inline std::atomic<int>& pending_usb_cleanups(){static std::atomic<int> count{0};return count;}
template<class State> Status close_usb_camera(State* s){
  if(!s->camera)return Status::success();
  const auto stopped=s->camera->stop();
  if(stopped)s->camera.reset();
  return stopped;
}
// Keeps the Engine, callback target and duplicated fd alive after an Activity goes away.
template<class State> void destroy_usb_state(State* s){
  ++pending_usb_cleanups();
  std::thread([s]{while(!close_usb_camera(s))std::this_thread::sleep_for(std::chrono::milliseconds(100));delete s;--pending_usb_cleanups();}).detach();
}
}
