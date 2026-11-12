# 模型资源

| 入口 | 是否需要权重 | 本次交付 |
|---|---|---|
| 2.0 实时深度 | C++ 使用原生深度和历史帧 | 相机标定与几何代码 |
| 2.0 RGB-D 回放 | YOLOv8s-seg | [ONNX 模型、来源、许可及校验](yolov8s-seg/README.md) |
| 可选离线 RGB-D 地面先验 | 需要 SegFormer-B0 ADE20K | [约 15 MB 权重、配置、许可及校验](segformer-b0-ade/README.md) |
| SAM 历史研究 | 选型对照 | [验证记录](../docs/vision/validation.md) |

相机标定参数与预训练权重是两类资源：真实相机运行时读取本机标定；测试夹具中的标定仅用于回归，不替代设备实测标定。
