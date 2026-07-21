# Vision Pipeline — 灵触·随行 视觉管线

摄像头采集 → 深度估计 → 9×10 SMA 点阵映射 → 90 字节帧 → 输出至 ESP32。

## 实时预览（无需 ESP32）

用电脑摄像头或手机摄像头实时体验深度检测效果。

### 电脑摄像头

```bash
cd vision
python live_preview.py
```

### Android 手机摄像头

手机和电脑连同一个 WiFi：

1. 手机安装 [IP Webcam](https://play.google.com/store/apps/details?id=com.pas.webcam) (免费)
2. 打开 App → 点 **Start server** → 底部会显示 `http://192.168.x.x:8080`
3. 电脑运行：

```bash
cd vision
python live_preview.py http://192.168.x.x:8080/video
```

界面三栏：**原始画面 | 深度热力图 | 9×10 SMA 点阵**。

| 按键 | 功能 |
|------|------|
| Q | 退出 |
| S | 切换点阵大小 |
| R | 切换 ROI 框 |

### 静态图片对比

```bash
cd vision
python generate_comparison.py
# 输出 → 浏览器打开 vision/data/compare/index.html
```

## 两种模式

| 模式 | 算法 | 依赖 | 硬件要求 |
|------|------|------|----------|
| **depth** | Depth Anything V2 单目深度估计 | PyTorch + transformers | RPi 5 (8GB) 或 GPU |
| **edge** | Canny 边缘 + 轮廓 + 网格投影 | OpenCV only | RPi Zero 2 即可 |

### Depth 模式管线

```
Depth Anything V2 → 深度值取反(高=近) → 裁切ROI(去天空/地面)
→ 每行P25基线 → 每格P85障碍得分 → 底部惩罚(抑制地面)
→ 双阈值二值化(Q78强/Q65弱+邻域) → 上限30 → 小连通区过滤
→ 9×10 SMA点阵(90字节)
```

## 环境配置

```bash
# 基础依赖
pip install opencv-python numpy scipy

# 深度估计依赖（depth 模式）
pip install torch torchvision transformers Pillow huggingface_hub
```

## 使用方法

```bash
# Depth 模式 — USB 摄像头 → 串口输出
python main.py --mode depth --camera 0 --output serial --serial-port /dev/ttyUSB0

# Depth 模式 — 文件记录（无 ESP32 时测试）
python main.py --mode depth --camera 0 --output file

# Edge 模式 — Canny 边缘 + 轮廓
python main.py --mode edge --camera 0 --output file

# 开启可视化 debug 窗口
python main.py --mode depth --camera 0 --debug
```

## 数据流

```
  ┌──────────┐      ┌──────────────┐      ┌───────────┐      ┌──────────┐
  │  Camera   │─────▶│  Processor   │─────▶│  Mapper   │─────▶│  Sender  │
  │ USB/RPi   │      │ depth / edge │      │ depth→grid│      │ serial/  │
  │ 640×480   │      │              │      │ 90 bytes  │      │ file/net │
  └──────────┘      └──────────────┘      └───────────┘      └──────────┘
```

## 输出帧格式

90 字节，对应 90 个 SMA 点（9列×10行），行优先，自顶向下。

每字节：0 = 清除，1 = 激活（障碍物）。

```
Col:  0  1  2  3  4  5  6  7  8
Row 0 (远):  byte  0 ... byte  8
Row 1:       byte  9 ... byte 17
...
Row 9 (近):  byte 81 ... byte 89
```

## 参数说明

| 参数 | 值 | 说明 |
|------|-----|------|
| `GRID_COLS × GRID_ROWS` | 9×10 | 90个SMA点 |
| `OBSTACLE_MARGIN` | 0.60 | 障碍需比背景近这么多（视差单位） |
| `CELL_OBS_PERCENTILE` | 85 | 单元格内取P85作为"近像素"代表 |
| `BOTTOM_PENALTY` | 0.55 | 底部行线性惩罚强度 |
| `MAX_ACTIVATIONS` | 30 | 最多激活30/90个点 |
| 双阈值 | Q78 / Q65 | 强响应直接保留，弱响应需有强邻域 |
| `MIN_CLUSTER_SIZE` | 3 | 小于3个点的连通区被过滤 |

## 文件结构

```
vision/
├── live_preview.py      # 实时预览（电脑/手机摄像头）
├── generate_comparison.py # 静态图片对比生成
├── main.py              # 主入口，CLI + 实时循环
├── depth_estimator.py   # Depth Anything V2 + 简易启发式降级
├── edge_detector.py     # Canny 边缘 + 轮廓 + 网格投影
├── grid_mapper.py       # 深度图 → 9×10 网格 → 90 字节帧
├── output_sender.py     # 串口 / 文件 / 网络发送器
├── config.py            # 所有阈值、尺寸、模式配置
├── requirements.txt     # Python 依赖
└── data/                # 测试图片 + 对比输出
```

## License

继承主项目授权。
