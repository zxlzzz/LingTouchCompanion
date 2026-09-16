# 当前实验视觉通路

手机拍摄 → 米制深度 → 地面拟合 → 空间栅格或单点告警 → BLE。两种条件共用 `experiment_server.py`，输出映射分别位于 `topdown_pipeline.py` 和 `single_point/alert_pipeline.py`。

## 准备与启动

Python 依赖包括 PyTorch、NumPy、OpenCV、Pillow、Matplotlib、bleak、cryptography，以及 Depth Anything V2 自身依赖。本机使用 `D:\anaconda\envs\LING\python.exe`。

仓库根目录须另备 `Depth-Anything-V2/metric_depth/` 源码，权重放在：

```text
Depth-Anything-V2/metric_depth/checkpoints/depth_anything_v2_metric_hypersim_vitl.pth
```

以下命令均在仓库根目录执行：

```powershell
python visionss/phone_server.py            # 空间触觉，HTTPS 8760
python single_point/alert_server.py        # 单点告警，HTTPS 8761
```

加 `--no-ble` 可在不连接设备时运行。手机与电脑连接同一局域网，打开终端显示的 HTTPS 地址，接受本地证书并开始预览。

终端命令：`start [标签]` 开始连续试次，`stop` 停止，`snap` 单帧，`export` 保存一帧，`status` 查看状态，`q` 退出。

## 文件与工具

| 文件 | 用途 |
|---|---|
| `depth_runner.py` | 常驻加载深度模型 |
| `phone_camera.html` | 手机拍摄页面，由实验服务提供 |
| `frame_converter.py` / `scan_link.py` | 栅格转15字节、BLE连接与刷新确认 |
| `depth_server.py` | 配合根目录 `depth_preview.html`，默认本机 HTTP 8765 |
| `evaluate_obstacle_scenes.py` | 根据 manifest 重放场景，比较默认映射与指定配置 |
| `profiles/multi_obstacle_preview.json` | 多障碍预览配置；正式入口不自动启用 |

离线评估参数为 `--manifest <文件> --outdir <目录>`，可用 `--profile <文件>` 替换配置、`--infer` 重新推理。空间实验通过 `--topdown-profile <文件>` 显式加载配置。

## 输出与验证

默认周期约1秒；等待固件刷新完成后继续，连续3帧失败自动暂停。日志写入 `experiment_runs/`，默认不保存逐帧大文件。

输出为10行×9列，行从远到近；发送前做穿戴左右镜像。手机上传长边2048，转正后按宽度换算焦距；默认相机高度1.40 m。首次真机使用需核对旋转方向、视场和装配映射，离线回归不代替实机验证。

标定与地面材质限制见 [验证记录](../TOPDOWN_VALIDATION.md)。
