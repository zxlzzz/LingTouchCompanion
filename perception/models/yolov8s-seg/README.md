# YOLOv8s-seg · Android RGB-D 回放

`yolov8s-seg.onnx` 由 Ultralytics 8.3.161 将 [原始 YOLOv8s-seg 权重](https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8s-seg.pt) 导出，固定输入 `1×3×384×640`，opset 17。`yolo_model.json` 保存源与输出的 SHA-256、类别以及导出配置，`checksums.sha256` 用于校验 ONNX。

许可沿用 [Ultralytics YOLOv8 的 AGPL-3.0 许可](https://docs.ultralytics.com/models/yolov8/#licensing)，随附 [上游许可证](LICENSE.upstream)。模型再生使用 [`tools/export_yolo.py`](../../tools/export_yolo.py)，本项目推理、掩码处理和构建源码位于 [Android 工程](../../apps/android-cs30-live/README.md)。

APK 用 ONNX Runtime Android 1.20.0 在回放页推理。运行时依赖来自 Maven 坐标 `com.microsoft.onnxruntime:onnxruntime-android:1.20.0`。[ONNX Runtime 许可证](https://github.com/microsoft/onnxruntime/blob/v1.20.0/LICENSE)
