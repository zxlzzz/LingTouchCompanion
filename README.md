# 灵触·随行 · LingTouch Companion

将视觉信息转换为触觉阵列反馈的辅助感知项目。当前实验使用手机摄像头、电脑端深度推理和 ESP32-S3，输出为 15 个六点模组，共 90 个触点。

## 项目入口

| 目录 | 用途 |
|---|---|
| [visionss/](visionss/README.md) | 当前实验：米制深度、俯视栅格、BLE 传输与日志 |
| [single_point/](single_point/README.md) | 共用实验通路的单点告警对照条件 |
| [firmware/](firmware/README.md) | ESP32-S3 固件、引脚与通信协议 |
| [app/frontend/](app/frontend/README.md) | uni-app 手机应用 |
| [app/backend/](app/backend/README.md) | 地图、命令解析与视觉帧转发服务 |
| [vision/](vision/README.md) | 旧图像平面视觉管线，保留作回退 |

## 运行实验

在仓库根目录、配置好依赖的 Python 环境中运行：

```powershell
python visionss/phone_server.py
```

本机已验证环境为 `D:\anaconda\envs\LING\python.exe`。模型准备、手机连接与操作见 [实验说明](visionss/README.md)。

## 浏览器工具

| 文件 | 用途 |
|---|---|
| [depth_preview.html](depth_preview.html) | 图片深度预览；先运行 `python visionss/depth_server.py` |
| [ble_mobile_controller.html](ble_mobile_controller.html) | 手机 BLE 点阵控制，使用 ROT180 映射 |
| [ble_testbench.html](ble_testbench.html) | 点阵与帧数据调试，保留旧 PROD 映射 |

BLE 页面需要浏览器提供 Web Bluetooth；两种映射不同，须与实际装配方向对应。

离线标定和距离验证见 [TOPDOWN_VALIDATION.md](TOPDOWN_VALIDATION.md)，工具为 `validate_distance.py`、`check_balloon_depth.py` 和照片复制脚本 `prep_new_pics.py`。

模型、测试照片、实验输出、论文材料和本地协作记录不随 Git 上传；源码、HTML 工具与必要配置保留在仓库中。
