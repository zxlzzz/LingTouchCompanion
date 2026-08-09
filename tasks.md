# visionss/ — 俯视栅格管线接入说明

给 cc 的交接文档。**不修改 `vision/` 下任何文件**，新建同级目录 `visionss/`。
`vision/` 保留为旧的图像平面路径（grid_mapper），实验期不再使用，但不删、不改，作为回退。

## 目录布局（与 vision/ 对齐，便于对照）

```
LingTouchCompanion/
├── vision/                    # 旧路径，冻结，不动
│   ├── grid_mapper.py
│   ├── frame_converter.py
│   ├── phone_server.py
│   ├── scan_link.py
│   └── bench_test.py
└── visionss/                  # 新路径
    ├── topdown_pipeline.py    # 已有，直接搬进来
    ├── frame_converter.py     # 从 vision/ 复制一份，不 import 旧的
    ├── phone_server.py        # 从 vision/ 复制后改扫描回调
    ├── scan_link.py           # 从 vision/ 复制，基本不动
    ├── depth_runner.py        # 新增：封装 Depth-Anything-V2 推理
    └── README.md              # 记录 fx / CAM_H_TRUE / 环境说明
```

复制而非 import：两条路径完全独立，改 `visionss/` 不会有任何机会碰坏 `vision/`。
代价是 `frame_converter.py` 有两份，**`MODULE_ROT180` 和 `sth2.html` 的
`BIT_MAP`/`modSlot()` 必须三处同步**，改动时在 README 里记一笔。

## 数据流

```
按键(FFE3 notify 0x04)
  → 拍照 / 取当前帧 JPEG
  → depth_runner.infer(img) -> 米制深度 ndarray (H, W) float32
  → topdown_pipeline.depth_to_grid(depth, fx) -> np.ndarray shape (10, 9) dtype=bool
  → frame_converter.grid_to_bytes(grid) -> bytes[15]
  → BLE FFE1 write
```

唯一的接口约定就是中间那个 **10×9 bool 数组**：
row 0 = 最近(0.5m)，row 9 = 最远(5m)；col 0..8 = 方位角，左到右。
`grid_to_bytes` 的输入格式和 `vision/` 版完全一致，所以帧格式、
`MODULE_ROT180`、固件侧都不需要动。

`topdown_pipeline.py` 目前的 CLI / 可视化保留，只需额外暴露一个
`depth_to_grid(depth, fx, cam_h_true=1.40) -> (10,9) bool` 的函数供 server 调用。

## 关键参数（已标定，写死在 visionss/README.md 里）

- `fx = 3260`（Mate 50 Pro 主摄 1x 竖拍 3072×4096；换分辨率时按像素宽等比缩放）
- `CAM_H_TRUE = 1.40`（胸挂实测）
- 深度模型：Depth-Anything-V2 **Metric-Hypersim-vitl**
- 地面拟合：`GROUND_IMG_FRAC=0.25`，`REFIT_ROUNDS=3`，非对称剔除 `[-15cm, +5cm]`

## 场地约束（标定实验的操作结论，写进实验协议）

深色/黑色反光地面会让 metric depth 近距离绝对尺度失准。
**拍摄场地用浅色非反光地面，画面最下方 25%（地面拟合候选带）不得出现深色胶垫/黑布。**
健康指标：同一场地多张照片的 `scale` 离散度 CV < 10%。

## conda 环境

现有 `lingtouch` 环境的 numpy LAPACK 整体损坏（`np.linalg.*` 和 matplotlib
`savefig` 静默崩溃，退出码 127）。`topdown_pipeline.py` 里已有手写
`matvec()` / `smallest_eigvec_3x3()` / `_det3()` 绕开。

**允许新建环境，命名 `LING`**，装干净的 OpenBLAS numpy + torch + Depth-Anything-V2 依赖。
建好后把 `topdown_pipeline.py` 里那几处手写绕开**保留但加注释**（别急着换回
`np.linalg`，等 LING 里跑通一遍确认无误再说），并在 README 记录
`np.show_config()` 的输出。

## 验收标准

1. `python visionss/frame_converter.py` 自检通过（`MODULE_ROT180=True`）。
2. `python visionss/topdown_pipeline.py <某张.npy>` 输出 10×9 栅格 ASCII 预览，
   空场 = 0 个激活点，椅子 3m ≥ 3 个激活点。
3. `python visionss/phone_server.py --no-ble` 能从拍照走到栅格预览。
4. 打通 BLE 后，一次按键到点阵变化的**端到端延迟实测值**写进 README
   （这个数要写进论文，也要提前告知参与者）。

## 不在范围内

- 不动 `vision/` 任何文件
- 不动固件、帧格式、BLE 协议
- 不动 uni-app（实验期不用）
- 旧的 `OBS_FLOOR` / `MIN_CLUSTER_SIZE` 调参计划作废，不要迁移到 visionss