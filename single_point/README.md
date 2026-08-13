# single_point/ — 单点告警对照条件

**对照目的**：与 `visionss/`（10x9 俯视栅格，给方位）做 RQ1 对比。同一相机、同一深度模型
（Depth-Anything-V2 metric-hypersim-vitl）、同一相机标定（fx=3260px）、同一地面拟合算法，
只把"深度图怎么变成输出"从"俯视栅格"换成"身前一个矩形区域内有没有障碍物"——隔离的自变量
是"空间信息的价值"。设计动机和推导过程见仓库根目录 [1.md](../1.md)。

文献术语：single-point alert / binary obstacle warning。

## 检测区域

| 参数 | 值 | 说明 |
|---|---|---|
| 前向范围 | 0.5 – 2.5 m | 白杖近场之外、一步可达的距离 |
| 侧向范围 | ±0.35 m（70cm 身宽稍大） | 只关心正前方会撞到的 |
| 高度保留 | 0.10 – 1.80 m | 与 `visionss/topdown_pipeline.py` 一致，直接复用其常量 |

输出**只有一个模组**（M11，栅格第4行中间列，无死点）整体凸起或不凸起，不给方位信息——
这正是和 `visionss/` 实验条件之间唯一有意义的差异。

## 数据流

```
按键(FFE3 notify 0x04)
  → alert_server.capture_and_infer(): 手机拍一张原生分辨率JPEG(横版4096x3072)
  → to_portrait(): 转正成竖版 (与 visionss/phone_server.py 同一逻辑)
  → depth_runner.DepthRunner.infer() -> 米制深度 ndarray (与 visionss/ 同一个模型实例逻辑)
  → alert_pipeline.depth_to_alert(depth, fx) -> (obstacle, count, threshold) | None
  → alert_to_grid(obstacle) -> (10,9) 栅格，只有 M11 覆盖的 6 格被点亮或全灭
  → frame_converter.grid_to_bytes(grid) -> bytes[15]  (不需要镜像，中间列单点居中)
  → BLE FFE1 write
```

## 文件结构

```
single_point/
├── alert_pipeline.py   # 核心: depth -> (obstacle, count, threshold) | None
├── alert_server.py     # phone_server.py 的 alert 版, HTTPS服务 + BLE 下发, 端口 8761
└── README.md           # 本文件
```

**不新建** `frame_converter.py` / `scan_link.py` / `depth_runner.py` / `phone_camera.html` /
`topdown_pipeline.py` 的地面拟合部分——全部直接 `sys.path.insert` 指到 `visionss/` 复用。
两个对照条件共用同一套拍照、深度推理、BLE 下发基础设施，只有 `alert_pipeline.py` 这一层
是这份独有的。

## 用法

```bash
# 对照条件 (single-point alert)
cd single_point
python alert_server.py --no-ble          # 先离线测(控制台回车手动触发一次全流程)
python alert_server.py                   # 连设备

# 实验条件 (spatial grid, 已有)
cd ../visionss
python phone_server.py --no-ble
python phone_server.py
```

两个服务端口不同（8761 / 8760），可以同时开着方便切换调试，但正式跑实验时同一时间应该
只开一个，避免两边同时请求手机拍照互相打架。

跑深度推理用 `D:\anaconda\envs\LING\python.exe`（这台机器的 numpy/BLAS 状况见仓库根目录
CLAUDE.md）。

## 离线单帧自检

不启动服务，直接灌一张 `visionss/topdown_pipeline.py` 用过的 `.npy` 测试数据看告警结果：

```bash
python alert_pipeline.py --depth ../pics/ascii/xxx_depth.npy --fx 3260
```

## 待确认 / 可能要问 Hsinlung 的点

- `ALERT_MODULE = 10`（M11）是按"手掌中央能摸到、且无死点"选的，如果实验设计上想换一个
  更贴合"提醒手势"的模组位置，改 `alert_server.py` 里这一个常量即可，其余流程不用动。
- 前向下限 0.5m 沿用了 1.md 草案里"白杖近场之外"的说法；如果白杖实际有效范围不是这个数，
  改 `alert_pipeline.py` 的 `D_FWD_MIN` 就行。
- 侧向 ±0.35m（70cm）目前是固定值，没有做"体型自适应"，如果需要按参与者实际身宽调，
  这两个值需要在拍摄/实验协议里跟着变，不是代码层面的事。
