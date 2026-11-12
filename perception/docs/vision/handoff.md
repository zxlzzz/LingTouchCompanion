# 2.0 交接说明

从 [安装包](../../deliverables/vision/android/README.md) 和 [安卓使用](android_usage.md) 开始。2.0 支持 CS30 原生深度实时复核，以及导入配对文件后的端侧 YOLO 融合。两路输出 6 行 × 9 列，达到 K 才导出 1。

| 路径（相对 perception） | 内容 |
|---|---|
| `apps/android-cs30-live` | 实时 USB、回放、JNI 和导出 |
| `vision/core`、`vision/native` | 选帧、历史缓存、深度复核与几何 |
| `models/yolov8s-seg` | 回放 ONNX、类别、来源和许可 |
| `tests`、`tools` | 基础模拟夹具、自动回归和可选实拍样本准备 |
| `deliverables/vision/android` | 2.0 APK、SHA-256、历史安装包入口 |

本次内容在 perception 内。实时算法以现有 1.7 深度格式运行，回放使用同步 RGB 和配准 RAW。USB 模拟测试、Android 端推理和 K 导出结果见 [验证记录](validation.md)。实际接线、暖重插、帧率与场景准确率需用目标手机验收。
