# 视觉感知交付

当前交付为 **CS30 融合点阵 Android 2.0**。实时入口使用 640×480 原生深度，先复核可疑深度再发布点阵。RGB-D 回放使用配对文件，在手机上运行 YOLOv8s-seg 和几何融合。两种入口都按 K 导出 6 行 × 9 列 0/1 JSON。

| 内容 | 入口 |
|---|---|
| 安装包 | [deliverables/vision/android](deliverables/vision/android/README.md) |
| 交接范围与限制 | [docs/vision/handoff.md](docs/vision/handoff.md) |
| 使用与供电 | [docs/vision/android_usage.md](docs/vision/android_usage.md) |
| Pipeline | [2.0 深度复核与融合](docs/vision/fusion_2_0.md) |
| 环境、构建、测试 | [docs/vision/build_and_test.md](docs/vision/build_and_test.md) |
| 检查结果 | [docs/vision/validation.md](docs/vision/validation.md) |
| Android 源码 | [apps/android-cs30-live](apps/android-cs30-live/README.md) |
| 独立 C++ 核心 | [vision/core](vision/core/README.md)、[vision/native](vision/native/README.md) |
| 最小测试夹具与编码参考 | [tests/vision/fixtures](tests/vision/fixtures/README.md)、[tests/reference](tests/reference/README.md) |
| 模型与离线参考 | [models](models/README.md)、[lab/rgbd_offline](lab/rgbd_offline/README.md) |

所有新增代码、方案、模型、测试、安装包均在本目录。命令默认从 **perception 目录**执行；生成文件写入本目录 `.build/vision` 或应用的忽略目录，不随源码提交。

`native/` 和 `cs30/` 保留团队原有实现与协议材料，继续服务仓库根目录的旧 `core` 和外壳；本次实时应用使用独立的 `vision/core`、`vision/native`，不修改团队公共接口，也不链接旧核心。两套库具有相同命名空间，不应同时链接进一个应用。相机协议/标定材料由 `cs30/` 共用。

2.0 安装包、回放所需的 ONNX 模型、许可与验证摘要均随源码交付。原始实拍样本由使用者按需要在本机准备。
