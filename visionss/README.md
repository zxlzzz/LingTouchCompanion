# visionss/ — 俯视栅格管线（metric depth 版）

给 cc 接手用的交接文档。这是 [tasks.md](../tasks.md) 描述的新路径：Depth-Anything-V2
**metric** 深度 → `topdown_pipeline.py` 俯视地面拟合 → 10×9 栅格 → BLE。

`vision/` 保留为旧的图像平面路径（`grid_mapper.py` 相对深度阈值法），冻结不动，作为
回退——两条路径完全独立，改这里不会碰坏那边，细节见 `vision/README.md` 第9节
"已知问题"（真机同时出现漏检+误检，用户决定换思路，就是这份 visionss/）。

## 数据流（跟 tasks.md 一致，实现细节见下面各节）

```
按键(FFE3 notify 0x04)
  → phone_server.capture_and_infer(): 手机拍一张原生分辨率JPEG(3072x4096)
  → depth_runner.infer(img) -> 米制深度 ndarray (H, W) float32
  → topdown_pipeline.depth_to_grid(depth, fx) -> (10, 9) bool
  → frame_converter.mirror_grid_horizontal() -> 设备穿戴镜像
  → frame_converter.grid_to_bytes(grid) -> bytes[15]
  → BLE FFE1 write
```

## 关键参数（已标定，标定过程见根目录 TOPDOWN_VALIDATION.md）

| 参数 | 值 | 说明 |
|---|---|---|
| `FX` | 3260 px | Mate 50 Pro 主摄 1x 竖拍，在 **3072px 宽**原生照片上标定（门宽复测法） |
| `FX_BASE_WIDTH` | 3072 px | 手机拍照分辨率必须匹配这个值——**不做运行时缩放**，宁可警告也不自动换算 fx，少一个出错的地方（这是 2026-08-09 跟 Hsinlung 确认过的设计决定，见下面"和 vision/ 的架构差异"） |
| `CAM_H_TRUE` | 1.40 m | 胸挂实测相机高度，尺度锚定基准 |
| 深度模型 | Depth-Anything-V2 **Metric-Hypersim-vitl** | `Depth-Anything-V2/metric_depth/checkpoints/depth_anything_v2_metric_hypersim_vitl.pth`（1.3GB，不进git，需手动放好） |
| 地面拟合 | `GROUND_IMG_FRAC=0.25`，`REFIT_ROUNDS=3`，非对称剔除 `[-15cm,+5cm]` | 定义在 `topdown_pipeline.py` |
| `MODULE_ROT180` | `True` | 模组180°反装，见 `frame_converter.py` |

## 和 vision/ 的架构差异（重要，接手前必读）

1. **按需拍照，不是持续推流**。vision/ 那条路径的深度模型轻（small/base，25-98M参数），
   `phone_server.py` 一直在跑推理，按键只是从缓存里取一份现成栅格。这条路径的模型是
   metric-hypersim-**vitl**，重得多（实测数据见下面"实测延迟"），没必要每帧都跑，改成
   按键才触发一次"拍照→推理→栅格"。
2. **原生分辨率拍照，不是 640x480→320x240 压缩流**。`FX=3260` 是在 3072px 宽照片上标定的，
   分辨率必须对得上标定值。`phone_camera.html` 用 `getUserMedia({width:{ideal:3072},
   height:{ideal:4096}})` 拍原生分辨率单张照片（JPEG q0.9），不是每 300ms 传一次压缩小图。
3. **轮询式触发协议**（因为标准 `http.server` 没有服务器推消息给浏览器的机制，不想引入
   WebSocket 依赖）：手机每 200ms `GET /poll` 问一次"当前拍照请求编号"，编号变化就立刻拍一张
   发到 `POST /frame?gen=N`；电脑端 `capture_and_infer()` 先递增编号、`GET /poll` 让手机看到，
   然后阻塞等（超时 `CAPTURE_TIMEOUT_S=6s`）对应编号的照片到达。`/poll` 只传一个几字节的
   JSON，不占带宽；大图只在真的要拍的时候传一次。
4. `vision/config.py`、`grid_mapper.py`、`color_detector.py`、`depth_estimator.py` 这些
   都没有对应版本——俯视栅格不需要图像平面的 ROI/阈值调参，颜色专项通道这条路径目前也没有
   移植（真机测试后如果发现远距离弱信号问题重演，再考虑要不要加）。

## 实测延迟（占位，等真机 BLE 联调后 Hsinlung 填真实的"按键→点阵变化"端到端数字）

2026-08-09 用桌面 RTX 4060、离线模拟（不经过真实 BLE，直接灌已有测试照片调用
`capture_and_infer()` 内部同一套代码路径）量过的软件侧耗时，供预估参考，**不代表真机端到端
延迟**（真机还要加上手机拍照对焦、JPEG编码、局域网上传这几步，`capture_and_infer()`
打印的"拍照上传"那段耗时里包含了这些，真机测的时候直接看它的 print 输出就行，不用改代码）：

| 阶段 | 首次调用（含CUDA/cudnn首次kernel编译） | 预热后稳态 |
|---|---|---|
| 深度推理（vitl, 3072x4096输入） | ~13s | ~0.6-0.9s |
| topdown_pipeline 俯视栅格 | ~0.8-1.2s | ~0.8-1.2s |
| **软件侧合计** | **~14s** | **~1.5-1.9s** |

**`phone_server.py` 启动时已经加了一次 CUDA 预热调用**（灌一张假图跑一遍推理），把这个
~13s 的一次性开销挡在服务启动阶段，不会摊到使用者第一次真实按键上——但预热这一步本身
会让服务启动多花 10+ 秒，日志里会打印预热耗时，是预期行为不是卡死。

**TODO（Hsinlung）**：真机 BLE 联调后，把"按下物理按键"到"设备点阵实际变化"的端到端
延迟实测值填在这里替换这个占位表格——这个数要写进论文，也要提前告知参与者。

## 验收标准执行情况（对应 tasks.md）

1. ✅ `python visionss/frame_converter.py` 自检通过（`MODULE_ROT180=True`），180°反装映射
   和 `vision/frame_converter.py` 当前硬件验证过的映射逐位一致（自检里直接把两个角点的
   预期字节值写死断言，跟 vision/ 版数值相同）。
2. ✅ `depth_to_grid()` 用已有测试集 `.npy` 验证过：黑布空场（`empty1`）0 个激活点，
   椅子3m（黑布 `chair_3m` / 浅蓝地坪 `chair_3m_plain`）分别 17 / 34 个激活点，满足
   "空场=0，椅子3m≥3"。**已知例外**：混合材质空场照片 `empty3`（画面近处一截是深色胶垫，
   落在 RANSAC 地面候选带里）有24个误报激活点——这是 TOPDOWN_VALIDATION.md 里记录过的
   已知数据问题（候选带材质分界线卡在候选带起点附近），不是这次新引入的 bug，真机部署
   选浅色地面、且脚下也不能是深色材质就不会有这个问题。
3. ⏳ `python visionss/phone_server.py --no-ble` 的手动触发路径（控制台回车）已经在
   `capture_and_infer()` 层面离线验证过全链路能跑通（拍照模拟→深度推理→栅格→ASCII预览→
   导出 `data/exports/`），但还没有用真实手机打开 `phone_camera.html` 走一遍真实 HTTP 上传，
   需要 Hsinlung 拿手机连同一WiFi测一次。
4. ⏳ 真机 BLE 端到端延迟——见上面"实测延迟"一节，等真机联调。

## conda 环境

现有 `lingtouch` 环境的 numpy LAPACK 整体损坏（`np.linalg.*` 和 matplotlib `savefig`
静默崩溃，退出码127，详见根目录 CLAUDE.md）。`topdown_pipeline.py` 里已有手写
`matvec()`/`smallest_eigvec_3x3()`/`_det3()` 绕开，**这些绕开先保留，不要因为建了新环境就
急着换回 `np.linalg`**——等 `LING` 里确认真的没问题再考虑要不要切换成标准写法。

新建了 `LING` 环境，装干净的 OpenBLAS numpy + torch + Depth-Anything-V2 依赖（这个环境的
搭建过程、`np.show_config()` 输出、numpy 是否真的恢复正常，见下面这一节——会在建完之后
补上，别看到空着就以为没建）。

## 文件结构

```
visionss/
├── topdown_pipeline.py    # 米制深度 → 点云 → 地面拟合 → 高度过滤 → 俯视栅格
│                           # (CLI/可视化保留，新加 depth_to_grid() 供 phone_server 调用)
├── frame_converter.py     # 10x9栅格 <-> 15字节模组帧，MODULE_ROT180显式开关，
│                           # 独立于 vision/ 那份（远近行标签方向不同，见文件头注释）
├── depth_runner.py        # 封装 Depth-Anything-V2 metric 模型加载 + 单帧推理(常驻显存)
├── phone_camera.html      # 手机拍照页：原生3072分辨率、轮询式按需拍照(不是持续推流)
├── phone_server.py        # HTTPS服务 + /poll+/frame协议 + capture_and_infer() + 控制台手动触发
├── scan_link.py           # BLE侧：订阅扫描请求(0x04)、下发15字节到设备，基本照抄vision/版
└── README.md              # 本文件
```

## 同步提醒

`frame_converter.py` 现在有两份（`vision/frame_converter.py` 和这份），`MODULE_ROT180` /
`_BIT_MAP_ROT180` 如果以后因为硬件改装（比如模组真的翻回正装）需要改，**两份都要改**，
`sth2.html` 的 `gridToBytes()` 目前还是老的 prod（未反装）映射，没有跟着"180°反装"这次
改动同步——实验阶段 Web Bluetooth 调试页不依赖它验证映射正确性，但如果以后要让
`sth2.html` 也能测试真机，记得先把它的映射同步过来，不然会两边对不上又要debug半天。
