# CS30 实时点阵

当前视觉交付的安卓入口。支持已确认能安装 Android APK 的 HarmonyOS 4.x 或更早版本；最低 Android API 29，包含 ARM64 与 x86_64。

- USB 设备下拉选择，连接前请求 CAMERA/USB 权限。
- 手动模式：每次按钮处理下一张完整新帧。
- 自动模式：每 500 ms 选一帧处理；停止后保留最后结果。
- K 默认 3、范围 1–16；导出当前 K 对应的 6 行 × 9 列 0/1 JSON。
- 枚举列表暂缺或异常不再直接当作拔出；底层传输失效单独报告。
- 支持查看、导出 USB 诊断。

**本次手机接线反馈：扩展坞 PD 口接充电宝后可以使用。交付演示按这套外接供电方式接线。**

完整说明统一在 [docs/vision](../../docs/vision/README.md)。安装包位于 [deliverables/vision/android](../../deliverables/vision/android/README.md)。

Android Studio 可直接打开此目录，SDK 36、NDK r27c、CMake 3.22.1+、JDK 17、Gradle 8.14.3。`native/CMakeLists.txt` 直接构建仓库的 `core` 与 `perception/native`，不再需要原工作区、`.runtime` 副本或补丁生成脚本。

普通构建：`gradlew.bat :app:assembleDebug`（Windows）或 `./gradlew :app:assembleDebug`。便捷工具、独立 NDK、离线缓存和测试入口见 [构建与测试](../../docs/vision/build_and_test.md)。

生产 CMake 默认不构建模拟 USB 库；测试库和夹具仅进入独立 instrumentation APK。开发签名用于本轮安装演示；团队正式发布签名由负责人配置，未随文件交付。
