# 单点告警对照条件

共用 [实验视觉通路](../visionss/README.md) 的拍摄、深度推理、调度、日志和 BLE，仅将空间栅格输出替换为二值告警。

在仓库根目录运行：

```powershell
python single_point/alert_server.py
```

默认 HTTPS 8761；加 `--no-ble` 可不连接设备运行。终端操作与空间触觉条件一致。

`alert_pipeline.py` 检测前方0.5–2.5 m、左右各0.35 m、离地0.10–1.80 m范围；占据比例阈值0.035，至少8点。触发时点亮 M11 整个模组，输出位置由 `visionss/experiment_server.py` 中的 `ALERT_MODULE` 定义。

正式实验前需用实际障碍物核对阈值与检测范围。
