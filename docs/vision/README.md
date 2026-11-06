# 视觉模块交付入口

整理日期：2026-11-06。当前主线是 **CS30 原生深度 → 几何处理 → 9×6 点阵 → JSON**，CPU 运行，无需下载模型或训练。

| 要看什么 | 入口 |
|---|---|
| 负责人先读：范围、目录、验收边界 | [交接说明](handoff.md) |
| 输入、地面、10 cm/40 cm、K 与输出 | [pipeline](pipeline.md) |
| 手机上如何接线、采集和导出 | [安卓使用](android_usage.md) |
| 如何构建与重跑检查 | [构建与测试](build_and_test.md) |
| BUSY、Commit 38、假拔出与 PD 供电 | [USB 排障](usb_troubleshooting.md) |
| 电脑实测、模拟器、历史模型比较 | [验证记录](validation.md) |
| 可参考的现有系统和下一阶段方法 | [研究选型](research.md) |
| 哪些入口需要模型、已附哪些权重 | [模型资源](../../models/README.md) |

代码主入口：[实时安卓](../../apps/android-cs30-live/README.md)、[共享核心](../../core/README.md)、[视觉原生实现](../../perception/native)、[可选 RGB-D 原型](../../perception/lab/rgbd_offline/README.md)。
