cmake_minimum_required(VERSION 3.22)
project(cs30_live LANGUAGES C CXX)
set(CMAKE_CXX_STANDARD 17)
get_filename_component(REPOSITORY "${CMAKE_CURRENT_SOURCE_DIR}/../../.." ABSOLUTE)
set(LINGTOUCH_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(LINGTOUCH_WITH_LIBUSB ON CACHE BOOL "" FORCE)
add_subdirectory("${REPOSITORY}/vision/core" repository-core)
add_library(cs30_live SHARED live_bridge.cpp)
target_link_libraries(cs30_live PRIVATE lingtouch_engine lingtouch_cs30_libusb log)
lingtouch_target_defaults(cs30_live)

# This target is built only by the test helper and placed in the test APK.
option(LINGTOUCH_VISION_TESTS "Build simulated USB instrumentation library" OFF)
if(LINGTOUCH_VISION_TESTS)
  add_library(cs30_live_test SHARED live_bridge.cpp test_transport.cpp test_usb.cpp
    "${REPOSITORY}/vision/native/cs30_libusb/src/cs30_libusb_source.cpp")
  target_compile_definitions(cs30_live_test PRIVATE CS30_SIMULATION)
  target_include_directories(cs30_live_test PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}"
    "${REPOSITORY}/vision/native/cs30_libusb/include"
    "${REPOSITORY}/native/third_party/libusb/libusb")
  target_link_libraries(cs30_live_test PRIVATE lingtouch_engine log)
  lingtouch_target_defaults(cs30_live_test)
endif()
