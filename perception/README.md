# 视觉感知交付

当前入口是 **CS30 深度 → 几何检障 → 9×6 点阵**。支持设备选择、手动单帧、自动 2 次/秒、停止保持、K 调整（默认 3）及随 K 的 0/1 JSON 导出。实时 APK 不需要神经网络模型或 GPU。

| 内容 | 入口 |
|---|---|
| 安装包 | [deliverables/vision/android](deliverables/vision/android/README.md) |
| 交接范围与限制 | [docs/vision/handoff.md](docs/vision/handoff.md) |
| 使用与供电 | [docs/vision/android_usage.md](docs/vision/android_usage.md) |
| Pipeline | [docs/vision/pipeline.md](docs/vision/pipeline.md) |
| 环境、构建、测试 | [docs/vision/build_and_test.md](docs/vision/build_and_test.md) |
| 检查结果 | [docs/vision/validation.md](docs/vision/validation.md) |
| Android 源码 | [apps/android-cs30-live](apps/android-cs30-live/README.md) |
| 独立 C++ 核心 | [vision/core](vision/core/README.md)、[vision/native](vision/native/README.md) |
| 最小测试夹具与编码参考 | [tests/vision/fixtures](tests/vision/fixtures/README.md)、[tests/reference](tests/reference/README.md) |
| 可选离线 RGB-D 原型及模型 | [lab/rgbd_offline](lab/rgbd_offline/README.md)、[models](models/README.md) |

所有新增代码、方案、模型、测试、安装包均在本目录。命令默认从 **perception 目录**执行；生成文件写入本目录 `.build/vision` 或应用的忽略目录，不随源码提交。

`native/` 和 `cs30/` 保留团队原有实现与协议材料，继续服务仓库根目录的旧 `core` 和外壳；本次实时应用使用独立的 `vision/core`、`vision/native`，不修改团队公共接口，也不链接旧核心。两套库具有相同命名空间，不应同时链接进一个应用。相机协议/标定材料由 `cs30/` 共用。

方案均为 Markdown；完整数据集、开发环境、缓存和历史大文件未加入交付。模型仅供可选离线原型，许可见模型目录。
