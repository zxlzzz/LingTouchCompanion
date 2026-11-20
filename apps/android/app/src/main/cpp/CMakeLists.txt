# 安卓 JNI 库：把核心（core + perception + agent）和 libusb 取流编进来。
cmake_minimum_required(VERSION 3.22.1)
project(lingtouch_android LANGUAGES C CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# 仓库根 = 本目录往上 6 层（apps/android/app/src/main/cpp），随仓库一起移动
get_filename_component(LINGTOUCH_ROOT "${CMAKE_CURRENT_SOURCE_DIR}/../../../../../.." ABSOLUTE)

set(LINGTOUCH_WITH_LIBUSB ON CACHE BOOL "" FORCE)
set(LINGTOUCH_BUILD_TESTS OFF CACHE BOOL "" FORCE)
add_subdirectory("${LINGTOUCH_ROOT}/core" "${CMAKE_CURRENT_BINARY_DIR}/lingtouch_core")

add_library(lingtouch_jni SHARED jni_bridge.cpp cs30_sensor_adapter.cpp android_usb_transport.cpp)
target_link_libraries(lingtouch_jni PRIVATE usb-1.0 lingtouch_engine)
if(ANDROID)
  target_link_libraries(lingtouch_jni PRIVATE log)
endif()
lingtouch_target_defaults(lingtouch_jni)
