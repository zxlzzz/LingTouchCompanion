# 旧视觉管线

早期图像平面相对深度 / 边缘检测方案，保留作回退。当前米制深度实验使用 [visionss](../visionss/README.md)。

## 运行

依赖见 [requirements.txt](requirements.txt)。以下命令在仓库根目录运行：

```sh
python vision/phone_server.py --no-ble
python vision/main.py --mode edge --camera 0 --debug
```

`phone_server.py` 提供手机拍摄与 BLE 通路；去掉 `--no-ble` 可连接设备。`main.py` 支持 `depth` / `edge` 模式及文件、串口、HTTP等输出，完整参数见 `--help`。

## 工具

| 文件 | 用途 |
|---|---|
| `live_preview.py` | 摄像头实时预览 |
| `bench_test.py` | 驱动链调试 |
| `export_sample.py` / `generate_comparison.py` | 样本导出与对比图 |
| `calibrate_balloon_color.py` / `color_bias_test.py` | 旧颜色检测与偏差验证 |
| `frame_converter.py` / `scan_link.py` | 15字节帧转换与 BLE 连接 |

旧串口等输出路径与当前 BLE 固件不一定使用相同帧格式，接硬件前核对对应输出实现。生成数据位于 `data/`，不提交。
