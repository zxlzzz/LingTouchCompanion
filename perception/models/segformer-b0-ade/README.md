# SegFormer-B0 ADE20K：可选离线参考模型

用于 `lab/rgbd_offline` 的 RGB 地面候选分割。它只给几何拟合筛选候选像素，不输出米制距离、不替代深度测量，也未接入实时 APK。

## 来源与本地版本

- 上游：[nvidia/segformer-b0-finetuned-ade-512-512](https://huggingface.co/nvidia/segformer-b0-finetuned-ade-512-512)。
- 核对的上游 revision：`489d5cd81a0b59fab9b7ea758d3548ebe99677da`。本地权重 SHA-256 与该 revision 的上游 LFS SHA-256 一致；配置按本地实际使用副本逐文件记录在 `source.json`。
- 三个运行文件：`config.json`、`preprocessor_config.json`、`model.safetensors`，合计约 15 MB。没有重复附 PyTorch bin、ONNX 或下载缓存。
- 核对命令：`sha256sum -c checksums.sha256`；Windows 可用 `Get-FileHash` 对照。

## 从 perception 目录运行

先准备该原型的 Python 3.12 依赖，再运行：

```shell
python lab/rgbd_offline/cs30_web.py --model-dir models/segformer-b0-ade --open
```

输入仍由使用者提供同帧 960×540 RGB PNG 与 RGB 对齐深度 RAW。不是当前 APK 的 640×480 原生深度格式；详情见离线原型 README。

## 上游许可

模型卡链接的原始许可全文保存在 `LICENSE.upstream`，来源为 [NVlabs/SegFormer LICENSE](https://github.com/NVlabs/SegFormer/blob/master/LICENSE)。其 3.3 条限定研究/评估等非商业用途；不能将此模型标为 MIT 或默认作为商业发布模型。当前实时 APK 不包含或调用它。
