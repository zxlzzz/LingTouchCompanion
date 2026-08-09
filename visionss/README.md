# visionss/ — 俯视栅格管线（metric depth 版）

给 cc 接手用的交接文档。这是 [tasks.md](../tasks.md) 描述的新路径：Depth-Anything-V2
**metric** 深度 → `topdown_pipeline.py` 俯视地面拟合 → 10×9 栅格 → BLE。

`vision/` 保留为旧的图像平面路径（`grid_mapper.py` 相对深度阈值法），冻结不动，作为
回退——两条路径完全独立，改这里不会碰坏那边，细节见 `vision/README.md` 第9节
"已知问题"（真机同时出现漏检+误检，用户决定换思路，就是这份 visionss/）。

## 数据流（跟 tasks.md 一致，实现细节见下面各节）

```
按键(FFE3 notify 0x04)
  → phone_server.capture_and_infer(): 手机拍一张原生分辨率JPEG(横版4096x3072)
  → phone_server.to_portrait(): 转正成竖版(3072x4096), 见下面"手机摄像头是横版的"
  → depth_runner.infer(img) -> 米制深度 ndarray (H, W) float32
  → topdown_pipeline.depth_to_grid(depth, fx) -> (10, 9) bool
  → frame_converter.mirror_grid_horizontal() -> 设备穿戴镜像
  → frame_converter.grid_to_bytes(grid) -> bytes[15]
  → BLE FFE1 write
```

## 关键参数（已标定，标定过程见根目录 TOPDOWN_VALIDATION.md）

| 参数 | 值 | 说明 |
|---|---|---|
| `FX` | 3260 px | Mate 50 Pro 主摄 1x 竖拍，在 **3072px 宽**原生照片上标定（门宽复测法）。可用 `--fx` 命令行参数覆盖，见下面"手机摄像头是横版的" |
| `FX_BASE_WIDTH` / `FX_BASE_AR` | 3072 px / 0.75 | 标定时的宽度和长宽比。宽度可以变（`resolve_fx()` 按比例换算），**长宽比不能变**（变了说明传感器被裁切，视场角跟着变，直接拒绝这一帧，不瞎换算） |
| `CAPTURE_ROTATE` | `cv2.ROTATE_90_CLOCKWISE` | 手机传来的横版帧转正成竖版的方向，见 `to_portrait()`。方向对不对要看第一次真机实拍的 `data/exports/*/original.jpg`，见下面"手机摄像头是横版的" |
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
   长宽比必须对得上标定值。`phone_camera.html` 拍原生分辨率单张照片（JPEG q0.9），不是每
   300ms 传一次压缩小图——但拍到的是**横版**，电脑端转正，细节见下面"手机摄像头是横版的"。
3. **轮询式触发协议**（因为标准 `http.server` 没有服务器推消息给浏览器的机制，不想引入
   WebSocket 依赖）：手机每 200ms `GET /poll` 问一次"当前拍照请求编号"，编号变化就立刻拍一张
   发到 `POST /frame?gen=N`；电脑端 `capture_and_infer()` 先递增编号、`GET /poll` 让手机看到，
   然后阻塞等（超时 `CAPTURE_TIMEOUT_S=6s`）对应编号的照片到达。`/poll` 只传一个几字节的
   JSON，不占带宽；大图只在真的要拍的时候传一次。
4. `vision/config.py`、`grid_mapper.py`、`color_detector.py`、`depth_estimator.py` 这些
   都没有对应版本——俯视栅格不需要图像平面的 ROI/阈值调参，颜色专项通道这条路径目前也没有
   移植（真机测试后如果发现远距离弱信号问题重演，再考虑要不要加）。

## 手机摄像头是横版的（2026-08-09 真机联调踩出来的坑，接手前必读）

最初设计假设"手机拍照就该是竖版 3072x4096"，结果真机测试发现完全不是这么回事。
排查过程（省得以后重踩）：

1. `getUserMedia({width:{ideal:3072},height:{ideal:4096}})` 第一次给的是 **3072x3072**
   正方形——`resolve_fx()` 按长宽比拒绝了这一帧（设计正确，没有瞎猜）。
2. 查 `track.getCapabilities()`：宽 1-4096，高 1-**3072**。高度上限被锁在3072，说明这颗
   摄像头在 video 管线里被暴露成 4096x3072 的**横向**传感器模式，根本没有竖版档位。
3. 试过 `applyConstraints()` 强制指定 `width:2304,height:3072`（长宽比精确等于0.75）——
   `track.getSettings()` 读回来确实报告"成功"变成这个尺寸，**但服务端实际收到的上传帧是
   3072x2304（横版，4:3），跟 getSettings() 报的不一致**。这是已知的 Android WebView/Chrome
   getUserMedia 坑：`getSettings()` 不完全可信，实际帧内容以服务端收到的为准。
4. 试过 `screen.orientation.lock('portrait')`（在按钮点击的用户手势里调用，满足浏览器对
   方向锁 API 的调用时机要求）——**也没用**，摄像头照样给横版。
5. **结论：这台手机的浏览器摄像头就是拿不到竖版视频流，别再跟它较劲。**

**最终方案**：`phone_camera.html` 直接管浏览器要横版 `4096x3072`（`aspectRatio` 显式钉成
`4/3`，防止有些机型给成传感器裁切过的 16:9），电脑端 `phone_server.py` 的 `to_portrait()`
收到宽>高的帧就用 `cv2.rotate()` 转正成竖版——这是纯旋转不是裁切，同一块传感器读出，
视场角和像素间距都不变，`fx` 数值不受影响（`fx=fy` 各向同性）。

**这一步不只是为了好看，是必需的**：`ransac_ground()` 靠 `n[1]`（法向量的 y 分量）判断
地面法线是不是"大致朝上"，这个判据假设重力方向对应图像的 y 轴（竖版画面）。横版帧的
重力方向其实在 x 轴上，不转正的话地面拟合会直接失败（每帧都报"地面候选点不足"或者
拟合出一个乱七八糟的平面）。

**`CAPTURE_ROTATE` 方向还没有用真机验证过是顺时针还是逆时针**——默认给的是
`cv2.ROTATE_90_CLOCKWISE`，第一次真机联调成功后，**打开 `data/exports/最新时间戳/
original.jpg` 看一眼**：地面应该在画面下方、天花板在上方。如果反了（地面在上面），
把 `phone_server.py` 里的 `CAPTURE_ROTATE` 改成 `cv2.ROTATE_90_COUNTERCLOCKWISE`。

**还有一层没解决、需要留意的风险**：即使长宽比对上了 4:3，也不能 100%保证浏览器
`getUserMedia` 拿到的视场角（FOV）跟拍标定照片用的手机原生相机 App 完全一致——有些机型
两条 pipeline 走的甚至不是同一颗摄像头/同一套 1x 定义。`aspectRatio` 检查抓不住这种
"比例对但视场角不同"的情况，量出来的距离会系统性偏但看起来毫无破绽。**验证方法**：
真机联调后拿一张 `data/exports/.../original.jpg`（浏览器实际拍到、经过 `to_portrait()`
转正的那张），用老办法量一次已知宽度的门/柜（`fx = 像素宽 × 距离 / 实际宽度`）：
量出来接近 3260 说明浏览器和相机 App 视场角一致，标定可以直接继承；差得多的话，不要
改源码里的 `FX` 常量，用 `python phone_server.py --fx <新值>` 传进去，保留原始标定值
方便以后对比。

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
   `capture_and_infer()` 层面离线验证过全链路能跑通（拍照模拟→`to_portrait()`转正→深度推理
   →栅格→ASCII预览），包括专门模拟横版上传帧的回归测试，但还没有用真实手机走一遍完整的
   `getUserMedia`→HTTPS上传→`to_portrait()`。真机联调时第一件事是核对 `CAPTURE_ROTATE`
   方向对不对（看 `original.jpg` 里地面是不是在下方），见上面"手机摄像头是横版的"一节。
4. ⏳ 真机 BLE 端到端延迟——见上面"实测延迟"一节，等真机联调。

## conda 环境

现有 `lingtouch` 环境的 numpy LAPACK 整体损坏（`np.linalg.*` 和 matplotlib `savefig`
静默崩溃，退出码127，详见根目录 CLAUDE.md）。`topdown_pipeline.py` 里已有手写
`matvec()`/`smallest_eigvec_3x3()`/`_det3()` 绕开，**这些绕开先保留，不要因为建了新环境就
急着换回 `np.linalg`**——`LING` 里两边都能用，但没必要现在冒险重写已经验证过的代码去用
标准写法，等以后有空/有动机再考虑切换。

### LING 环境（2026-08-09 建好，已验证 numpy/matplotlib 恢复正常）

```
D:\anaconda\Scripts\conda.exe create -n LING python=3.11 -y
D:\anaconda\envs\LING\python.exe -m pip install torch==2.13.0+cu126 torchvision==0.28.0+cu126 \
    --index-url https://download.pytorch.org/whl/cu126
D:\anaconda\envs\LING\python.exe -m pip install opencv-python matplotlib scipy \
    huggingface_hub einops bleak cryptography
```

**numpy 2.4.4，`np.show_config()` 关键信息**：blas/lapack 都是 `scipy-openblas`
（OpenBLAS 0.3.31.188.0, USE64BITINT DYNAMIC_ARCH），不是 `lingtouch` 那个损坏的库。

**验证结果（跟 `lingtouch` 里会静默崩溃、退出码127的那几个操作逐一对照测过）**：
- `np.linalg.inv(np.eye(3))` ✅、`np.linalg.det(np.eye(3))` ✅
- `np.linalg.eigh()`（对称矩阵特征分解，`ransac_ground._refit()` 本来想用的写法）✅
- `np.linalg.svd()` ✅
- 大数组矩阵-向量乘法（20万×3 `@` 3维向量，`matvec()` 本来想绕开的那种规模）✅
- matplotlib `savefig()`（`topdown_pipeline.py --outdir` 那段四联图可视化依赖的路径）✅

**LING 环境彻底解决了这台机器的 numpy/BLAS 问题**，`topdown_pipeline.py --outdir` 的
四联图可视化现在用 `LING` 是能跑通的（之前在 `lingtouch` 里一直跑不通）。

**回归测试**：`visionss/frame_converter.py` 自检、`capture_and_infer()` 全链路离线模拟
（拍照模拟→`DepthRunner`→`depth_to_grid`→ASCII预览）都在 `LING` 里重新跑过一遍，
和 `lingtouch` 环境的输出数值完全一致（同一张测试照片，10个激活点，栅格分布逐格相同）。
torch 2.13.0+cu126，`torch.cuda.is_available()=True`，识别到 RTX 4060 Laptop GPU。

**以后跑 visionss/ 下的东西，用 `D:\anaconda\envs\LING\python.exe`**，不用再迁就
`lingtouch` 那个坏环境（`vision/` 那条旧路径还是继续用 `lingtouch`，两边环境也互不干扰）。

## 文件结构

```
visionss/
├── topdown_pipeline.py    # 米制深度 → 点云 → 地面拟合 → 高度过滤 → 俯视栅格
│                           # (CLI/可视化保留，新加 depth_to_grid() 供 phone_server 调用)
├── frame_converter.py     # 10x9栅格 <-> 15字节模组帧，MODULE_ROT180显式开关，
│                           # 独立于 vision/ 那份（远近行标签方向不同，见文件头注释）
├── depth_runner.py        # 封装 Depth-Anything-V2 metric 模型加载 + 单帧推理(常驻显存)
├── phone_camera.html      # 手机拍照页：横版4096x3072原生分辨率、轮询式按需拍照(不是持续推流)
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
