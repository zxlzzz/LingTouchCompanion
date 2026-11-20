# perception — CS30 感知

| 目录 | 内容 |
|---|---|
| [native/](native/README.md) | C++：CS30 协议、标定解码、取流会话 `cs30_capture`（相机驱动的共用部分）、拆帧、深度几何、地面拟合、9×6 的 0/1/2；旧 `cs30_libusb` 只剩鸿蒙一个默认关闭的诊断选项在用 |
| [cs30/](cs30/README.md) | CS30 免 SDK 取流的协议材料（10/25 在电脑上做的结论、启动序列、标定 blob、参考帧） |
| [lab/](lab/README.md) | Python 实验位：可选的离线 RGB-D 原型 |
| [models/](models/README.md) | 离线原型用的模型 |

相机驱动只有一套：共用部分是 `native/` 的 `cs30_capture`，平台部分在 `apps/android`、`apps/harmony` 的 `cs30_sensor_adapter` 和 `*_usb_transport`，接口是 `core/include/lingtouch/modules.h` 的 `SensorAdapter`。实现和限制见 [CS30 手机端采集说明](../docs/cs30_mobile_capture.md)。

视觉同学 11/06 交付的独立实时 App（`android-cs30-live`、`vision/core`、`vision/native`、APK 和对应文档）已不再使用，移到 [archive/perception_cs30_live](../archive/perception_cs30_live/README.md)。其中 [usb_troubleshooting.md](../archive/perception_cs30_live/docs/vision/usb_troubleshooting.md) 记有手机实测的重连处理，主驱动目前还没有。
