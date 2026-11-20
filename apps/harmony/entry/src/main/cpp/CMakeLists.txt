# 鸿蒙 Node-API 库 libentry.so：把核心（core + perception + agent）编进来。
cmake_minimum_required(VERSION 3.16)
project(lingtouch_harmony LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# 仓库根 = 本目录往上 6 层（apps/harmony/entry/src/main/cpp），随仓库一起移动
get_filename_component(LINGTOUCH_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../../../../../.." ABSOLUTE)

# 旧离线诊断接口的可选依赖。主应用通过系统 usbSubmitTransfer 取流。
option(LINGTOUCH_HARMONY_LIBUSB "Build the getFileDescriptor + libusb alternative" OFF)

set(LINGTOUCH_BUILD_TESTS OFF CACHE BOOL "" FORCE)
set(LINGTOUCH_WITH_LIBUSB ${LINGTOUCH_HARMONY_LIBUSB} CACHE BOOL "" FORCE)
add_subdirectory("${LINGTOUCH_ROOT}/core" "${CMAKE_CURRENT_BINARY_DIR}/lingtouch_core")

add_library(entry SHARED napi_init.cpp camera_napi.cpp cs30_sensor_adapter.cpp harmony_usb_transport.cpp)
target_link_libraries(entry PUBLIC libace_napi.z.so lingtouch_engine)
if(LINGTOUCH_HARMONY_LIBUSB)
  target_compile_definitions(entry PRIVATE LINGTOUCH_HARMONY_LIBUSB=1)
  target_link_libraries(entry PUBLIC lingtouch_cs30_libusb)
endif()
lingtouch_target_defaults(entry)

# Real-time capture/geometry must stay optimized even when deployed with Run.
# Keep symbols and the shared strict floating-point rules for diagnostics.
option(LINGTOUCH_HARMONY_OPTIMIZE "Optimize real-time native processing" ON)
if(LINGTOUCH_HARMONY_OPTIMIZE AND CMAKE_CXX_COMPILER_ID MATCHES "Clang|GNU")
  foreach(target entry lingtouch_base lingtouch_perception lingtouch_engine)
    target_compile_options(${target} PRIVATE -O2)
  endforeach()
endif()
