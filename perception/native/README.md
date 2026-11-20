# perception/native — CS30 取流与 9×6 栅格（视觉同学）

C++17，无平台依赖，由 [`core/CMakeLists.txt`](../../core/CMakeLists.txt) 编进 `lingtouch_engine`。协议依据是 [`perception/cs30/REPORT.md`](../cs30/REPORT.md)。

## 流程

```
等时包 ──按批──▶ UvcFrameAssembler ──614400 字节──▶ DepthPipeline
                                                    ├─ 过滤：0、恰为 1、<100 mm、>5 m、畸变不可逆的像素；相位绕回孤立近点；边缘飞点
                                                    ├─ 反投影（光轴 Z / 径向可切换，去畸变可开关）
                                                    ├─ 地面拟合（RANSAC + 最小二乘；失败 → 整张 2）
                                                    └─ 地面坐标 → 高度带 0.10–1.90 m → 9×6 的 0/1/2
```

| 文件 | 内容 |
|---|---|
| `cs30_protocol.h/.cpp` | 常量、启动序列表、IN 响应收集（设备信息、两份标定分片拼接） |
| `cs30_capture.h/.cpp` | 相机驱动的共用部分（相机同学）：取流会话、流格式、双流载荷解析；平台部分在 `apps/*/` 的 `cs30_sensor_adapter`、`*_usb_transport`，说明见 [docs/cs30_mobile_capture.md](../../docs/cs30_mobile_capture.md) |
| `src/cs30_startup_sequence.inc` | 由 `tools/gen_startup_sequence.py` 从 `perception/cs30/startup_sequence.json` 生成，不手改 |
| `uvc_frame_assembler.h/.cpp` | 拆帧：UVC 头、FID 翻转、EOF、ERR、空包；与 `independent_proof.py` 逻辑一致 |
| `cs30_calibration.h/.cpp` | 标定 blob 无 schema 解码（字段含义为推断，见头文件注释） |
| `depth_geometry.h/.cpp` | 去畸变查表与像素过滤 |
| `ground_fit.h/.cpp` | 地面拟合、相机坐标 → 地面坐标 |
| `occupancy.h/.cpp` | 0/1/2 规则 |
| `pipeline.h/.cpp` | 串起来；另有平面检查（判断深度是光轴 Z 还是径向、要不要去畸变） |
| `tools/lt_frame_tool.cpp` | 主机小工具：对一帧原始深度打印栅格或平面检查 |
| `cs30_libusb/` | 旧的 libusb 取流，主驱动不用；只剩鸿蒙默认关闭的诊断选项 `LINGTOUCH_HARMONY_LIBUSB` 链接它 |
| `third_party/libusb/` | libusb 源码；安卓传输层直接用（`LINGTOUCH_WITH_LIBUSB=ON` 时编译） |

## 未确认、做成参数的

- 深度是光轴 Z 还是径向距离：`depth.meaning`。平面检查用合成数据验证过能区分，真机还没测。正对墙只能区分 Z 和径向；要判断去不去畸变，得斜着拍一个平面（例如地面）。
- 片上是否已经去过畸变：`depth.undistort`。
- 深度图本身是否左右镜像：`depth.image_mirrored`。
- 所有门槛（高度带、地面容差、1 的支持点数、0 允许缺的小块数、过滤参数）都在 `core/config/lingtouch_defaults.conf`。

## 测试

在仓库根目录：

```bash
cmake -S core -B build/core -G Ninja && cmake --build build/core && ctest --test-dir build/core --output-on-failure
```

- `test_uvc_assembler`：合成包流（FID 翻转、EOF、错误位、空包、坏头、丢包、超长、按批传入）。
- `test_cs30_protocol`：启动表与 REPORT 一致；标定分片乱序拼接。
- `test_calibration`：两份 blob 的解码结果。
- `test_depth_geometry`：去畸变查表回投误差；各过滤器。
- `test_geometry_synthetic`：合成场景（地面 + 箱子、细杆、高度带外物体、无地面、横滚），断言箱子格 1、身后 2、看全地板 0；平面检查。
- `test_reference_frames`：3 张真实参考帧不崩、输出确定、打印栅格（这 3 帧是近场数据，地面拟合会失败，整张 2）。
- `test_engine`：启动响应 → 标定 → 合成等时包 → 后台出栅格 → 15 字节帧。

对任意一帧（例如 PC 上 `independent_proof.py` 存下的 `depth_NNN.raw`）：

```bash
build/core/perception_tests/lt_frame_tool plane perception/cs30/reference_000.bin perception/cs30/calibration_0.bin
```
