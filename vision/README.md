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
→ 双阈值二值化(Q85强/Q72弱+邻域/同排列连续确认) → 上限12
→ 小连通区过滤 → 行跨度压缩(≤2行) → 颜色专项通道叠加(可选)
→ 9×10 SMA点阵(90字节)
```

具体每一步的取值和调整原因见下面「本轮改动记录 / 现状与已知问题」。

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

以下是当前 `config.py` / `grid_mapper.py` 里的实际值（不是最初设计值，经过多轮实测调整，见下面"本轮改动记录"）。

| 参数 | 值 | 说明 |
|------|-----|------|
| `GRID_COLS × GRID_ROWS` | 9×10 | 90个SMA点 |
| `OBSTACLE_MARGIN` | 0.85 | 障碍需比所在行背景基线近这么多（视差单位） |
| `CELL_OBS_PERCENTILE` | 85 | 单元格内取P85作为"近像素"代表 |
| `BOTTOM_PENALTY` | 0.55 | 底部行线性惩罚强度 |
| `OBS_FLOOR` | 0.4 | score 绝对下限，排名靠前但达不到这个绝对值也不算 |
| `MAX_ACTIVATIONS` | 12 | 最多激活12/90个点（原来是30→22→12，逐步收紧） |
| 双阈值 | Q85 / Q72 | 强响应直接保留，弱响应需有强邻域或同排/列连续命中 |
| `MIN_CLUSTER_SIZE` | 2 | 小于2个点的连通区被过滤（深度通道） |
| `MAX_CLUSTER_ROW_SPAN` | 2 | 每个连通区最多跨2行（行=远近编码，单个物体不该跨太多"距离层"） |
| `BALLOON_HUE_RANGE` (color_detector.py) | (21, 33) | 气球颜色识别，H∈[0,179]，实测约52~56°黄偏橙 |
| `BALLOON_SAT_MIN` / `BALLOON_VAL_MIN` | 71 / 178 | 颜色识别的饱和度/亮度下限 |

## 文件结构

```
vision/
├── live_preview.py           # 实时预览（电脑/手机摄像头，纯预览不接设备）
├── phone_server.py           # 手机浏览器摄像头 → HTTPS → 电脑处理 → 预览 + 可选 BLE 下发
├── phone_camera.html         # phone_server.py 提供给手机浏览器的采集页面
├── scan_link.py              # BLE 侧：订阅扫描请求、下发90点帧到 ESP32
├── frame_converter.py        # 90点扁平帧 <-> 15字节模组帧（设备物理位映射）
├── main.py                   # CLI 主入口，depth/edge 模式 + serial/file/http/network 输出
├── depth_estimator.py        # Depth Anything V2 + 简易启发式降级
├── edge_detector.py          # Canny 边缘 + 轮廓 + 网格投影（轻量备用管线）
├── grid_mapper.py            # 深度图 → 9×10 网格 → 90 字节帧（核心检测逻辑）
├── color_detector.py         # 颜色专项识别通道（已知物体，不依赖深度，远距离也能用）
├── output_sender.py          # 串口 / 文件 / 网络发送器
├── config.py                 # 所有阈值、尺寸、模式配置
├── export_sample.py          # 抓一帧导出全套中间结果（原图/深度/逐格分数/颜色掩码），排查用
├── calibrate_balloon_color.py # 对实物取色，算出 color_detector.py 该填的 HSV 阈值
├── generate_comparison.py    # 静态图片批量对比生成
├── bench_test.py             # 不接视觉，直接发已知图案到板子，校验打包/物理位映射
├── requirements.txt          # Python 依赖
└── data/                     # 测试图片 + 对比输出 + export_sample 导出（exports/ 不进 git）
```

## 本轮改动记录 / 现状与已知问题

这是一轮很长的迭代（BLE 修复 → 画质优化 → 阈值调参 → 颜色通道），记录下来方便之后接手的人（包括未来的自己）不用重新踩一遍坑。**结论先说：真机 BLE 实测同时出现了漏检和误检，判定当前这条"深度估计为主"的路线不够可靠，用户决定换个思路，这条线暂停在这里。**

### 1. BLE 控制链路修复（最早的 1.patch）
- `grid_mapper.py`：`MIN_CLUSTER_SIZE` 3→2（避免 4-5m 处椅子这类小物体被整块删掉）；加了 `OBS_FLOOR` 绝对下限（当时是 0.0，后面又调整过，见第5节）。
- `phone_server.py`：`from grid_mapper import depth_map_to_xy_frame` 是失效引用（函数已改名/重构），改成 `depth_map_to_dot_frame`；`latest_braille` 加时间戳，超过 1.5s 不下发，防止相机断流后按键拿到旧画面。
- `scan_link.py`：`_on_scan` 加 2.5s 去抖，规避固件中断路径的 `prevData` 失步 bug 导致连击误触发。

### 2. 镜像位置修复
最初镜像逻辑写在 `depth_map_to_dot_frame()` 内部，导致预览画面（面板3点阵图）和面板1/2 方向不一致——而这个函数的输出同时给"屏幕预览"和"发给设备"两个不同用途，镜像应该只在后者生效。改成：`depth_map_to_dot_frame()` 保持摄像头视角不镜像，新增 `mirror_frame_horizontal()`，只在真正打包发给硬件前（`phone_server.py` 存 `latest_braille` 时、`main.py` 的 `sender.send()` 前）调用一次。

### 3. GPU + base 模型
默认用的是 CPU + small 模型（2-3 FPS，画质糊）。机器上其实有 RTX 4060，但 conda 环境 `lingtouch` 装的是 CPU-only 版 torch，代码里也硬编码 `use_gpu=False`。改法：
- 装 `torch==2.13.0+cu126` / `torchvision==0.28.0+cu126`（跟已装的 CPU 版本号完全对应，从 `https://download.pytorch.org/whl/cu126` 装）。
- `phone_server.py` / `live_preview.py` 改成 `DepthEstimator(model_size="base", use_gpu=True)`。
- `depth_estimator.py` 里有个自动切换 HF 镜像站的逻辑（探测到能连 hf-mirror.com 就用），但机器上跑着代理（TUN 模式，127.0.0.1:7897），镜像站在这种环境下会 308 重定向到真实 huggingface.co 从而被 huggingface_hub 拒绝。启动时手动设 `HF_ENDPOINT=https://huggingface.co` 覆盖掉自动镜像逻辑即可（代理本身能直连真实站点）。

### 4. 手机浏览器黑屏修复
现象：手机锁屏/切后台后摄像头被系统回收，回来之后画面一直黑，清缓存也没用。根因不是缓存，是 `phone_camera.html` 原来的逻辑没有"摄像头掉了要重新拿"这一环——`stream` 变量非空就不会重新 `getUserMedia`，哪怕这个 stream 早就死了。修复：加了 `track.ended` 监听、`visibilitychange` 时主动探测重连、画面连续黑屏的看门狗（采样亮度），外加一个手动"重连摄像头"按钮。顺手给 `phone_server.py` 的 HTML 响应加了 `Cache-Control: no-store`，避免以后手机缓存住旧页面。

### 5. 反光/褶皱假阳性修复
现象：拍一块反光褶皱的黑色塑料布地板（没有真实障碍物），9×10 点阵却大片凸起。根因：`CELL_OBS_PERCENTILE`(P85)+`OBSTACLE_MARGIN`(0.60)+双阈值(Q78/Q65)+`OBS_FLOOR`(0.0) 这套组合对局部反光/褶皱造成的非几何噪声太敏感。调整过程（用合成场景反复验证）：
- `OBSTACLE_MARGIN` 0.60→0.85，双阈值 Q78/Q65→Q85/Q72，`OBS_FLOOR` 0.0→0.4：这三处一起把"排名靠前但绝对值很小"的假信号挡掉。
- `CELL_OBS_PERCENTILE` 一度降到 75 想进一步压噪声，但代价是把细长物体（长条气球）自己的信号也滤没了（气球本来就只占格子宽度一小部分，P75 要求 25% 像素偏近，气球没那么宽）；扫参数验证后改回 85——真正压噪声靠的是上面那三处，不依赖"物体占格子比例"，所以 85 反而是两头都不牺牲的取值。

### 6. 细长物体检测（`_run_confirmed`）
双阈值的"weak 格子需要 strong 邻居撑腰"规则对细长物体不友好——细长气球单格信号可能连 strong 门槛都摸不到，但会连续好几格都在 weak 附近。加了 `_run_confirmed()`：同排或同列连续 ≥2 格命中 weak，不需要 strong 邻居也直接确认。反光噪声空间上乱跳，很难连续两格以上排成一条直线，所以这条规则理论上不会引入新的假阳性（合成测试验证过）。

### 7. 保守化 / 减少同时凸起
用户反馈"凸起太多画面/触感会乱"。改动：
- `grid_mapper.py` 新增 `MAX_CLUSTER_ROW_SPAN=2`：行在这套编码里代表远近，单个物体理论上只在一个距离出现，每个连通区在行方向压缩到最多2行（保留活跃格子最密的那一段），不是真的距离信息，只是检测过程带来的富余。
- 原来"每个连通区整体膨胀一圈保证摸得到"改成"只把真正孤立的单格补成2格"，已经有面积的区域不再额外放大。
- `MAX_ACTIVATIONS`（config.py）22→12。

合成测试对比（同样场景）：真实障碍物 16→6、竖放气球18px 12→2、横放气球14px 10→4，空场景/反光噪声始终是0，没有牺牲检出。

### 8. 颜色专项识别通道
用户明确"场景里只会出现长条气球和椅子"这个封闭条件后，加了一条不依赖深度、只看颜色的专项通道，用来兜底深度信号在远距离（实测约2m开外）弱到测不出来的情况：
- `color_detector.py`：按 HSV 色相/饱和度/亮度识别，跟深度管线是"任一测到就点亮"的 OR 叠加关系，不是替换。故意绕开了"连通区太小当噪声删掉"的规则（颜色信号本身已经是强证据，哪怕只点亮一个格子也该信），但还是会走行跨度压缩和孤点补齐这两步保持输出风格一致。
- `calibrate_balloon_color.py`：对着实物气球点几下鼠标取色，自动算出建议的 HSV 阈值。已经用真实气球标定过一次：`BALLOON_HUE_RANGE=(21,33)`（黄偏橙，不是最早猜的紫色），`BALLOON_SAT_MIN=71`，`BALLOON_VAL_MIN=178`。
- `phone_server.py`（含 `E` 键导出）、`live_preview.py`、`main.py`、`export_sample.py`、`generate_comparison.py` 都已经把原始 BGR 画面传给 `depth_map_to_dot_frame(depth_map, frame_bgr=...)`，颜色通道自动生效；不传 `frame_bgr` 时行为完全不变（纯深度管线）。
- `export_sample.py` / `phone_server.py` 的 `E` 键导出现在多存一个 `color_mask.jpg`（白=颜色命中的像素），方便看颜色通道具体在哪触发。

### 9. 已知问题（重要，接手前必读）
- **合成场景全部测试通过，真机不行**：空场景、反光噪声、竖放/横放气球（不同宽度/对比度）、椅子代理这些合成测试全部符合预期，但实际接 BLE 板子测试时同时出现了**漏检**（该亮不亮）和**误检**（到处乱亮、跟实物对不上）。说明这一整套基于 Depth Anything V2 相对视差的阈值调参思路，对真实环境（实际光照、材质反光、手机摄像头压缩噪声、自动曝光跳动）的泛化能力不够——合成场景没能覆盖真实世界的复杂度，调参本质上是在拟合我搭的合成测试集，不是在拟合真实分布。
- **颜色通道还没交叉核对椅子颜色**：只标定了气球，没有确认 `BALLOON_HUE_RANGE=(21,33)` 是否会被椅子颜色命中。
- **颜色通道跟暖光反光有潜在冲突**：黄偏橙、高亮度（V≥178）的判定条件，跟暖光灯下光滑表面的高光在色相/亮度上比较接近——第5节修的那类"反光误判"问题，理论上也可能在颜色通道重演，还没实测验证过。
- **深度估计的物理限制**：近距离（1-2m内）表现相对稳定，但距离越远，物体本身的视差信号越弱，最终会跟背景噪声同量级，这是方法本身的限制，不是继续调参能解决的。
- 用户决定暂停这条路线，考虑换用背景差分、形状识别等对光照/材质更鲁棒的经典 CV 方法，或者重新评估要不要继续依赖单目深度估计——具体往哪个方向走还没有定论。

## License

继承主项目授权。
