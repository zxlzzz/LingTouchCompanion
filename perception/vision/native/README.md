# 实时深度与 USB 实现

本实现由 [../core](../core/README.md) 构建，供当前 `android-cs30-live` 使用。它与团队原有 `perception/native` 分开，避免改变公共核心。协议依据共用的 [cs30/REPORT.md](../../cs30/REPORT.md)。

| 阶段 | 实现 |
|---|---|
| 打开与启动 | 平台先 force claim；`cs30_libusb_source` 接 fd 并执行启动表 |
| 接收与拼帧 | `uvc_frame_assembler`：等时包/UVC 头、FID、EOF、ERR → 640×480 uint16 深度 |
| 标定与反投影 | `cs30_calibration`、`depth_geometry`：标定解析、过滤、去畸变、3D 点 |
| 地面与栅格 | `ground_fit`、`pipeline`：RANSAC/最小二乘、离地高度带、0/1/2 证据 |
| K 点阵 | `vision/core/src/depth_evidence.cpp` 汇总 10 cm 小格；每个 40 cm 格有 16 小格 |

启动序列表由 `tools/gen_startup_sequence.py` 读取 `perception/cs30/startup_sequence.json` 生成；当前路径以 perception 目录为基准。生成器只更新代码表，不手抄协议。

从 perception 目录用 `python tools/host_test.py` 运行全套核心测试；详见 [构建与测试](../../docs/vision/build_and_test.md)。真实参考帧仍使用团队 `cs30/` 中的原始文件，测试兼容其历史路径字段，不改动证据。

第三方 libusb 保持独立动态库。Linux 等时提交的 `ENOMEM` 由本地修订保留为 `LIBUSB_ERROR_NO_MEM`。安卓 fd 路径每笔提交 8 个 3072 字节微帧，分配失败后排空队列并在同一接口上逐级降到 4 或 2 个。 [libusb 版本与修订说明](../../native/third_party/libusb/README.lingtouch.md)

参数在 `vision/core/config/lingtouch_defaults.conf`。深度含义、去畸变和镜像仍是可配置项；无可信地面时输出未知，不能将空心点解读为已确认的自由空间。USB 回归使用模拟传输，不能代替手机供电、内核和真实相机验收。
