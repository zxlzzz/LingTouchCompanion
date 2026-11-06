# perception — CS30 感知（视觉同学）

| 目录 | 内容 |
|---|---|
| [native/](native/README.md) | C++：CS30 取流协议与拆帧、标定解码、深度几何、地面拟合、9×6 的 0/1/2；安卓用的 libusb 取流 |
| [cs30/](cs30/README.md) | CS30 免 SDK 取流的协议材料（10/25 在电脑上做的结论、启动序列、标定 blob、参考帧） |
| [lab/](lab/README.md) | Python 实验位（视觉同学的 Windows 原型和 SpatialLM 复现不在本仓库） |

## 本次视觉交付

- 当前 CPU 深度链路：`native`，共享数据类型与线程在根目录 `core`。
- 构建/测试：[`tools`](tools/README.md)。
- 可选 RGB-D 历史参考：[`lab/rgbd_offline`](lab/rgbd_offline/README.md)，所需 SegFormer 权重已在根目录 `models/segformer-b0-ade`，原始数据不随包。
- 最终方案及验证：[`docs/vision`](../docs/vision/README.md)。

新增小格证据与旧 `cells` 保持区分，K 影响当前点阵/JSON，旧 BLE 发送不自动使用 K。
