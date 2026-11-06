# apps — App 外壳（交互同学）

| 目录 | 内容 |
|---|---|
| [android/](android/README.md) | Kotlin，经 JNI 调核心；USB 授权 → libusb 取流、BLE、前台服务 |
| [harmony/](harmony/README.md) | ArkTS（Stage 模型），经 Node-API 调核心；usbSubmitTransfer 取流（备选 fd + libusb）、BLE、长时任务。平板优先 |

外壳只放界面和只能用平台接口的东西（USB 打开与授权、蓝牙、录音放音、读屏、后台保活、地图显示）；其余都在 C++ 核心里，以后加 iOS 只多一层 Swift 外壳。旧的 uni-app 工程在 `archive/app/frontend/`。
