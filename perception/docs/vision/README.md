# 视觉模块交付入口

当前版本为 **CS30 融合点阵 2.0**。实时深度复核和配对 RGB-D 回放均在手机 CPU 上运行。

| 要看什么 | 入口 |
|---|---|
| 负责人先读：范围、目录、验收边界 | [交接说明](handoff.md) |
| 输入、反光复核、YOLO、10 cm/40 cm 与输出 | [2.0 pipeline](fusion_2_0.md) |
| 手机上如何接线、采集和导出 | [安卓使用](android_usage.md) |
| 如何构建与重跑检查 | [构建与测试](build_and_test.md) |
| BUSY、Commit 38、假拔出与 PD 供电 | [USB 排障](usb_troubleshooting.md) |
| 2.0 模拟器和历史模型比较 | [验证记录](validation.md) |
| 可参考的现有系统和下一阶段方法 | [研究选型](research.md) |
| 哪些入口需要模型、已附哪些权重 | [模型资源](../../models/README.md) |

代码主入口：[实时安卓](../../apps/android-cs30-live/README.md)、[独立视觉核心](../../vision/core/README.md)、[视觉原生实现](../../vision/native)、[可选 RGB-D 原型](../../lab/rgbd_offline/README.md)。
