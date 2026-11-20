# apps/android — 安卓外壳（交互同学）

Kotlin，不依赖 AndroidX。外壳只放只能用平台接口的东西：USB 授权与打开、蓝牙、前台服务、界面；取流协议、拆帧、栅格、点阵编码都在 C++ 核心里（经 JNI 调 `core/include/lingtouch/engine.h`）。

```
MainActivity → CAMERA / USB 授权 → StreamService 的相机工作线程
   ├─ AndroidCs30SensorAdapter → 系统 force claim / 授权 fd → libusb 等时接收
   │  → 共用 Cs30CaptureSession → 深度 + JPEG → Engine 后台算栅格
   └─ HandleLink：BLE FFE0，写 FFE1（15 字节），FFE3 通知刷新完成 / 按键
```

实现和限制见 [CS30 手机端采集说明](../../docs/cs30_mobile_capture.md)。默认 640×480 深度 + 960×540 彩色，前台服务及 wake lock 支持后台采集；实际供电和息屏行为需逐机验收。

## 编译（本地）

用 Android Studio 打开 `apps/android/`，或在该目录运行：

```bash
./gradlew assembleDebug
```

需要 JDK 17/21、Android SDK 35、NDK 27.0.12077973、CMake 3.22.1（SDK Manager 里装）。版本：AGP 8.7.3、Kotlin 2.0.21、Gradle 8.11.1、minSdk 29、只编 arm64-v8a。入口库显式使用 C++17，NDK 开启 `ANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES`，同时兼容 4 KB/16 KB 内存页。native 部分由 `app/src/main/cpp/CMakeLists.txt` 把仓库里的 `core/` 整体编进来，另出一个独立的 `libusb-1.0.so`（LGPL，不静态链接）。

完整检查命令为 `./gradlew assembleDebug lintDebug`。调试 APK 位于 `app/build/outputs/apk/debug/app-debug.apk`，已有调试签名，可传到 Android 10 及以上、支持 ARM64 和 USB OTG 的手机安装。

2026-11-18 已在 Windows 使用 OpenJDK 21、上述 SDK/NDK/CMake 完成 Kotlin、原生编译、APK 打包及 Lint（0 错误、19 警告，主要为中文文本、图标及已有后台运行提示）。CTest 14/14 通过，安卓 USB 传输层包含 7 项回归：关闭等真实回调排空、部分提交失败后减小请求、I/O/内存错误的有界尝试、其他错误不降级、异常长度/包数、重提失败，以及控制请求失败不修改出参。成品已通过 APK v2 签名校验、ARM64 动态库依赖检查、ELF LOAD 16 KB 对齐及 `zipalign -c -P 16`；预览帧的 Java 构造函数签名与 JNI 一致。当前没有连接安卓手机，真实 USB、预览和息屏采集仍待验收；鸿蒙真机连接成功不能替代安卓验收。

首次构建工具下载在仓库忽略的 `.build/android-tools/`，SDK 路径写在本地忽略的 `local.properties`，没有修改系统环境变量。Android Studio 用户按自己的 SDK 路径重新配置即可。

USB 默认最多每请求 8 包（24 KiB），10 个并行请求；同步提交遇到 `LIBUSB_ERROR_IO`/`LIBUSB_ERROR_NO_MEM` 时，先取消并等待真实回调完成，再按 8→4→2→1 包有界尝试。其他错误立即返回。包描述校验保留原始槽位偏移，异常包丢弃受影响帧；数量不符则报告中断。该策略减少手机端大请求的压力，但通用 I/O 错误不等于已确认内存不足，真实原因仍需日志。

## 界面

- 连接相机 → 异步启动深度和彩色，收到带标定的完整帧后显示正在接收；9×6 栅格按行显示（· 空、■ 障碍、? 未知），每行的读屏文字是“第 N 行（X 到 Y 米）：空，障碍，未知…”。
- 新增与鸿蒙一致的彩色/深度预览：彩色 JPEG 在独立线程解码，深度按固定 0.1–5 m 显示为近亮远暗、无效黑色，每秒最多更新 5 次。只显示同组真实采集帧；停止、重连及切到后台清除旧画面并丢弃旧解码结果，不改变感知输入。
- 主状态与逐帧诊断分开，详细比例每秒更新，状态变化立即显示。地面拟合失败仍整张未知，没有放宽 5%/10 cm 等判定门槛。
- USB 授权回调校验待处理请求、设备 ID 和真实权限；取消连接后迟到的授权不会重新打开相机。预览与平面检查的原生访问由服务工作线程串行，避免关闭后访问旧句柄。
- 没连设备显示“未连接”；没有的值不显示（帧率只在开流后用实测帧数计算）。
- 状态 2 的触点表示（平 / 凸）待 Hsinlung 定：配置里没设定时不预选，必须手选才能发帧。
- “持续发送”供真机后台测试：每次手柄刷新完成（或 1.5 s 超时）后发最新一帧。
- “平面检查”：对着平整的墙或斜看地面，比较光轴 Z / 径向、去不去畸变四种假设的平面残差。
