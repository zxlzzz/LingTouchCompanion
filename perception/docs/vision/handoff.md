# 负责人交接说明

## 入口与范围

当前交付是 **CS30 深度接收 → 几何检障 → 9×6 黑白点阵**。设备下拉选择；手动一次取一帧；自动按 500 ms 选帧；停止后保持结果。K 默认 3，可调；JSON 跟随 K，达到阈值为 1，否则为 0。

以下路径均相对 perception：

| 目录 | 用途 |
|---|---|
| `apps/android-cs30-live` | Kotlin UI、USB 权限/force claim、JNI、实时入口 |
| `vision/core` | 独立处理线程、采集门控、小格证据、K 点阵和 JSON |
| `vision/native` | USB 协议、拆帧、标定、过滤、地面与栅格 |
| `tools` | 主机测试、安卓构建与模拟 USB 回归、PC 连接工具 |
| `tests` | 约 474 KiB 回归夹具、旧板编码参考 |
| `deliverables/vision/android` | APK、SHA-256 和安装说明 |
| `docs/vision` | 方案、使用、构建、排障和紧凑验证记录 |
| `lab/rgbd_offline`、`models` | 可选历史 RGB-D 原型及约 15 MB SegFormer 权重/配置/许可 |

实时 APK 不用模型、GPU、训练或厂商 SDK 安装器。只附离线原型实际使用的 SegFormer，不带未接入的 YOLO/SAM 权重、完整数据集、环境、缓存或历史报告。原工作区保留。

## 与团队仓库的边界

旧交付 PR #6 已合并，因此本次 PR 在 perception 外会有撤销记录：移除旧根目录视觉附加文件，恢复 README、公共 core 和旧 Android 外壳到视觉交付前版本。迁入后的全部实现、文档、测试、模型、安装包都在 perception。

团队原有 `perception/native` 和 `cs30` 保留原样，继续配合根目录旧 core；新应用独立使用 `vision/core` 与 `vision/native`，不依赖根目录 agent/experiments。两套核心不同时链接。原生鸿蒙主路径未改，新应用目前交付 Android APK（支持 APK 的 HarmonyOS 4.x 或更早）。

新实时入口保留串行连接/关闭、平台 force claim、传输取消后回收、停止冻结和重新枚举。旧 `OccupancyGrid.cells`/BLE 编码含义未变；K 点阵目前用于界面与 JSON，未改旧手柄协议。

## 验收边界

本次编译与回归结果见 [validation.md](validation.md)。模拟 USB 检查软件一致性；真实 Windows 相机历史完成 6 轮、489 帧完整接收。用户确认手机扩展坞 PD 口接充电宝后可用，尚未登记具体机型/系统小版本、长时运行和手机实测帧率。

算法仍依赖可信地面，离地不足 10 cm 的障碍、楼梯/落差没有完整覆盖；未观测区不代表安全，近于 1 m 不在本点阵范围。没有加入 SLAM/IMU、RGB 配准、YOLO/SAM 或路径规划。软件回归不能替代真实场景精度验收。
