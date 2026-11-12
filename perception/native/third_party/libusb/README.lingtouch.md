# libusb（第三方）

- 版本：1.0.29，来自 <https://github.com/libusb/libusb/releases/download/v1.0.29/libusb-1.0.29.tar.bz2>
- 压缩包 SHA-256：`5977fc950f8d1395ccea9bd48c06b3f808fd3c2c961b44b0c2e6e29fc3a70a85`
- 许可：LGPL-2.1 或更高版本（`COPYING`）。作者见 `AUTHORS`，上游说明见 `README`。
- 只取了 Linux/Android 后端需要的文件：`libusb/{core,descriptor,hotplug,io,strerror,sync}.c` 与头文件、`libusb/os/{linux_usbfs,linux_netlink,events_posix,threads_posix}.{c,h}`；`config/config.h` 来自上游 `android/config.h`。
- 本地修订位于 `libusb/os/linux_usbfs.c`。等时 `SUBMITURB` 返回 `ENOMEM` 时保留内核日志，并返回 `LIBUSB_ERROR_NO_MEM`，供 CS30 应用按分配失败处理。
- 编译方式与上游 `android/jni/libusb.mk` 相同的文件清单，改用 CMake（本目录 `CMakeLists.txt`），产物是单独的 `libusb-1.0.so`。不要把它静态链进核心或 JNI 库：LGPL 要求发布时使用者能替换这个库。

安卓上的用法照上游 `android/README`：初始化时设 `LIBUSB_OPTION_NO_DEVICE_DISCOVERY`，再用 `libusb_wrap_sys_device` 包住 `UsbDeviceConnection.getFileDescriptor()` 拿到的 fd，见 `perception/native/cs30_libusb/`。
