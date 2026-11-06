# apps — App 外壳（交互同学）

| 目录 | 内容 |
|---|---|
| [android/](android/README.md) | Kotlin，经 JNI 调核心；USB 授权 → libusb 取流、BLE、前台服务 |
| [harmony/](harmony/README.md) | ArkTS（Stage 模型），经 Node-API 调核心；usbSubmitTransfer 取流（备选 fd + libusb）、BLE、长时任务。平板优先 |

外壳只放界面和只能用平台接口的东西（USB 打开与授权、蓝牙、录音放音、读屏、后台保活、地图显示）；其余都在 C++ 核心里，以后加 iOS 只多一层 Swift 外壳。旧的 uni-app 工程在 `archive/app/frontend/`。

## 当前视觉演示入口

[android-cs30-live](android-cs30-live/README.md) 是本次 CS30 深度点阵 APK：手动/自动采集、K 与 JSON，不依赖 RGB 模型。原 `android` 保留旧 BLE/读屏调试，`harmony` 为原生鸿蒙入口；三者用途不同。视觉交接见 [docs/vision](../docs/vision/README.md)。
