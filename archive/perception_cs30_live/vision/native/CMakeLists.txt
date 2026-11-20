# 视觉同学的 C++ 部分：CS30 取流协议与拆帧、标定解码、深度几何、地面拟合、9×6 的 0/1/2。
# 由 core/CMakeLists.txt add_subdirectory；不单独作为顶层工程使用。
add_library(lingtouch_perception STATIC
  src/cs30_protocol.cpp
  src/cs30_calibration.cpp
  src/uvc_frame_assembler.cpp
  src/depth_geometry.cpp
  src/ground_fit.cpp
  src/occupancy.cpp
  src/pipeline.cpp)
target_include_directories(lingtouch_perception
  PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include"
  PRIVATE "${CMAKE_CURRENT_SOURCE_DIR}/src")
target_link_libraries(lingtouch_perception PUBLIC lingtouch_base)
lingtouch_target_defaults(lingtouch_perception)

# libusb 等时传输取流（安卓用；桌面 Linux 也能编，便于主机上检查）
if(LINGTOUCH_WITH_LIBUSB)
  add_subdirectory("${PERCEPTION_ROOT}/native/third_party/libusb" "${CMAKE_CURRENT_BINARY_DIR}/third_party/libusb")
  add_subdirectory(cs30_libusb)
endif()
