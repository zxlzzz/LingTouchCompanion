# LingTouch · Companion（灵触·随行）

面向视障用户的触觉导航辅助设备。通过白杖挂件形式，将深度视觉信息实时转化为 9*10 盲文模块阵列的触觉反馈，帮助用户感知前方障碍物分布。

## 系统组成

| 模块 | 目录 | 说明 |
|------|------|------|
| 手机 App | `app/frontend/smart_cane/` | uni-app（Vue），负责导航、语音交互、BLE 通讯 |
| 后端服务 | `app/backend/smart_cane_server/` | Node.js，百度地图路径规划、AI 助手接口 |
| 视觉管线 | `vision/` | Python，运行于树莓派，深度估计 + 障碍物检测 |
| 固件 | `firmware/` | Arduino，ESP32-S3 驱动 15 模块盲文点阵 |

## 硬件概要

- **触觉输出**：15 个 WUJIE SMA 盲文模块（3×5 排列，共 90 触点），通过 74HC595 级联 + ULN2803A 驱动
- **主控**：ESP32-S3 DevKitC-1（N16R8），BLE 连接手机
- **视觉**：树莓派 + 摄像头，运行 Depth Anything V2 深度估计
- **供电**：VCC 3.2V（线圈）、VCCS 2.0V（SMA），外部可调 DC-DC 模块

## 快速开始

各模块的环境配置与运行方式详见对应目录下的 README.md。

## 目录结构

```
LingTouch-Companion/
├── README.md
├── .gitignore
├── app/
│   ├── backend/smart_cane_server/   # Node.js 后端
│   └── frontend/smart_cane/         # uni-app 前端
├── vision/                          # 树莓派视觉管线
│   └── data/                        # 测试用 jsonl 数据
└── firmware/                        # ESP32-S3 固件
    └── braille_15module_prod/
```
