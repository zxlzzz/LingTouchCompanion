# Vision Pipeline — 灵触·随行 视觉管线

树莓派视觉模块：摄像头采集 → 深度估计/边缘检测 → 3×5 网格映射 → 15 字节盲文帧 → 输出至 ESP32。

## 两种模式

| 模式 | 算法 | 依赖 | 硬件要求 | 参考 |
|------|------|------|----------|------|
| **depth** | Depth Anything V2 单目深度估计 | PyTorch + transformers | RPi 5 (8GB) 或 GPU | 项目设计目标 |
| **edge** (默认) | Canny 边缘 + 轮廓检测 + 网格投影 | OpenCV only | RPi Zero 2 即可 | CHI '25 "Seeing with the Hands" |

### Depth 模式

输入 RGB → Depth Anything V2 推理 → 深度图 (米) → 每个网格单元取 min depth → 根据距离阈值编码 braille dot pattern：

| 距离 | 盲文点阵 | 含义 |
|------|---------|------|
| < 0.5m | 0x3F (全部6点) | 紧急避障 |
| 0.5–1.0m | 0x2F (4点) | 警告注意 |
| 1.0–2.0m | 0x09 (2点) | 轻度感知 |
| > 2.0m | 0x00 (无) | 路径畅通 |

### Edge 模式 (论文方法)

RGB → 灰度 → 二值化(阈值90) → 高斯模糊(5×5) → Canny 边缘 → 轮廓过滤(>1000px²) → 多边形近似 → 3×5 网格投影 → 每个网格开/关 → 根据行位置编码盲文点阵。

完全复现 Teng et al., CHI '25, Section 4.2, Figure 3(d) 的视觉管线。

## 环境配置

```bash
# 基础依赖（edge 模式）
pip install opencv-python numpy pyserial

# 深度估计依赖（depth 模式，额外安装）
pip install torch torchvision transformers Pillow huggingface_hub einops
```

## 使用方法

```bash
# Edge 模式 — USB 摄像头 → 串口输出
python main.py --mode edge --camera 0 --output serial --serial-port /dev/ttyUSB0

# Depth 模式 — USB 摄像头 → 文件记录
python main.py --mode depth --camera 0 --output file

# 单张图片测试（验证管线）
python main.py --mode edge --image test.jpg

# 开启可视化 debug 窗口
python main.py --mode edge --camera 0 --debug
```

## 数据流

```
  ┌──────────┐      ┌──────────────┐      ┌───────────┐      ┌──────────┐
  │  Camera   │─────▶│  Processor   │─────▶│  Mapper   │─────▶│  Sender  │
  │ USB/RPi   │      │ depth / edge │      │ depth→grid│      │ serial/  │
  │ 640×480   │      │              │      │ 15 bytes  │      │ file/net │
  └──────────┘      └──────────────┘      └───────────┘      └──────────┘
```

## 输出帧格式

15 字节，对应 15 个盲文模块（3列×5行），与 ESP32 固件 `braille_15module_prod.ino` 的 `FRAME_LEN=15` 对齐。

```
Byte  0: 模块 1  (top-left)     Byte  1: 模块 2  (top-center)   Byte  2: 模块 3  (top-right)
Byte  3: 模块 4                 Byte  4: 模块 5                 Byte  5: 模块 6
Byte  6: 模块 7                 Byte  7: 模块 8                 Byte  8: 模块 9
Byte  9: 模块 10                Byte 10: 模块 11                Byte 11: 模块 12
Byte 12: 模块 13                Byte 13: 模块 14                Byte 14: 模块 15 (bottom-right)
```

每字节：bit0–bit5 = 6 个 SMA 盲文点，bit6–bit7 保留。

## 文件结构

```
vision/
├── main.py              # 主入口，CLI + 实时循环
├── camera.py            # USB 摄像头 / 文件源抽象
├── depth_estimator.py   # Depth Anything V2 + 简易启发式降级
├── edge_detector.py     # Canny 边缘 + 轮廓 + 网格投影（论文方法）
├── grid_mapper.py       # 深度图/边缘 → 3×5 网格 → 15 字节盲文帧
├── output_sender.py     # 串口 / 文件 / 网络发送器
├── config.py            # 所有阈值、尺寸、模式配置
├── requirements.txt     # Python 依赖
└── data/                # 测试图片数据
```

## 与论文的对应关系

| 论文 (CHI '25) | 本项目 |
|----------------|--------|
| 5×6 电触觉电极 (30个) | 3×5 SMA 盲文模块 (15个, 各6点) |
| 腕部摄像头，手背触觉 | 白杖摄像头，手部触觉 |
| Canny 边缘 → 二值开/关 | Edge 模式支持 + Depth Anything V2 |
| 场景理解导航 | 避障 + 导航双模式 |
| Electro-tactile 脉冲 | SMA 四相驱动时序 |

## License

继承主项目授权。
