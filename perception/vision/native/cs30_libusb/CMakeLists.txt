# libusb 等时传输取流（安卓用；桌面 Linux 也能编）。链接单独的 libusb-1.0.so。
add_library(lingtouch_cs30_libusb STATIC src/cs30_libusb_source.cpp)
target_include_directories(lingtouch_cs30_libusb PUBLIC "${CMAKE_CURRENT_SOURCE_DIR}/include")
target_link_libraries(lingtouch_cs30_libusb PUBLIC lingtouch_engine usb-1.0)
lingtouch_target_defaults(lingtouch_cs30_libusb)
