# apps — App 外壳（交互同学）

| 目录 | 内容 |
|---|---|
| [android/](android/README.md) | Kotlin，经 JNI 调核心；USB 授权、BLE、前台服务 |
| [harmony/](harmony/README.md) | ArkTS（Stage 模型），经 Node-API 调核心；usbSubmitTransfer 取流、BLE、长时任务。平板优先 |

两端的相机驱动（`cs30_sensor_adapter`、`*_usb_transport`、鸿蒙 `camera_napi`、`ets/usb/`、`ets/camera/`、安卓 `StreamService` 和 `CameraPreview` 里的取流部分）归相机同学，和 `perception/native/cs30_capture` 是同一套，说明见 [docs/cs30_mobile_capture.md](../docs/cs30_mobile_capture.md)。

外壳只放界面和只能用平台接口的东西（USB 打开与授权、蓝牙、录音放音、读屏、后台保活、地图显示）；其余都在 C++ 核心里，以后加 iOS 只多一层 Swift 外壳。旧的 uni-app 工程在 `archive/app/frontend/`。
