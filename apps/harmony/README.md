# apps/harmony — 鸿蒙外壳（交互同学，平板优先）

ArkTS，Stage 模型。外壳只放只能用平台接口的东西：USB 授权与传输、蓝牙、长时任务、界面；启动表、拆帧、栅格、点阵编码都在 C++ 核心里（经 Node-API 调 `libentry.so`，源码 `entry/src/main/cpp/napi_init.cpp`）。

```
pages/Index.ets
 ├─ usb/Cs30Usb.ets → cameraOperation（异步）→ HarmonyCs30SensorAdapter
 │   → 原生 USB 请求经 TSFN 回到系统 usbManager → usbSubmitTransfer
 │   → 带会话号的批量回调 → 共用 Cs30CaptureSession → 深度 + JPEG → Engine
 ├─ device/HandleLink.ets  BLE FFE0 / FFE1 / FFE3
 └─ common/KeepAlive.ets  系统长时任务（需要真实满足任务类型条件）
```

实现与限制见 [CS30 手机端采集说明](../../docs/cs30_mobile_capture.md)。默认 640×480 深度 + 960×540 彩色。原有 fd 实验接口保留，但主界面已改为连接、重启取流、断开；libusb 可选依赖默认关闭。

## 编译（本地，DevEco Studio）

打开 `apps/harmony/`，配置签名后运行。`compatibleSdkVersion` / `targetSdkVersion` 都是 `5.1.0(18)`：`usbSubmitTransfer`、`UsbDataTransferParams`、等时传输类型在 OpenHarmony 文档里都是 API 18 起。DevEco 装的 SDK 更新时可以只调高 `targetSdkVersion`。`modelVersion` 沿用 9/29 比赛版工程的 `6.0.0`，与 DevEco 版本不符时按 IDE 提示改。

native 部分由 `entry/src/main/cpp/CMakeLists.txt` 把 `core/` 编进 `libentry.so`。系统传输使用 API 18，原生控制请求在工作线程等待，ArkTS 事件循环执行平台调用。

2026-11-18 已用本机 DevEco Studio / SDK 26.0.1 Beta1 完成原生 C++17、ArkTS 编译及签名 HAP 打包。已在主机跑过 `tools/napi_host_test.js` 和 `tools/camera_host_test.js`。后者运行真实采集控制器和真实 Node 插件，用模拟系统 USB 验证异步双流、取消排空、断线恢复、授权失败和小批次降级；模拟 USB 不能代替真机。

HUAWEI MatePad Pro DAL-W00（HarmonyOS 7.0.0 / API 26）已安装运行过，但接相机开流失败；系统日志为 `submiturb failed, errno=12`。当前修复将单请求从 96 KiB 改为最多 24 KiB，遇到同步提交 I/O 错误 `14400012` 时等待取消排空，再按 8→4→2→1 包有限重试，保留每包 3072 B 和双流分辨率。修复版已通过签名 HAP 构建，尚待覆盖安装后确认真机首帧；界面诊断包含每请求大小及尝试序列。此 API 错误码也可能有其他原因，需结合系统日志判断。

后续实测进入等时回调，但因包描述中检测到负长度而停止。当前回调层会校验包数、槽位长度和实际长度，将异常包标为错误以丢弃坏帧并继续接收，偏移布局异常时丢弃整批。诊断保留坏包数及首个异常数值；原生保护仍保留，持续无完整帧仍在 5 秒后报错。已通过模拟坏包后的双流恢复、持续坏包超时及 DevEco 编译，并通过 HDC 覆盖安装、启动该版，真机首帧仍待接回相机复测。

随后“包 8”出现在只有 8 包的请求中，定位该次负长度为原生描述数组读取越界：OpenHarmony 的 `napi_get_typedarray_info` 返回字节数，原代码按 Node 的元素数语义再次乘 4。现由 `cpp/napi_bytes.h` 统一处理两平台长度单位并检查底层容量、偏移和对齐；主取流路径直接传描述的 ArrayBuffer。已通过标准 Node 和模拟鸿蒙字节数语义两套真实插件测试及 DevEco HAP 构建，等待该修复的真实相机复测。

主机测试插件的构建需同时包含 `napi_init.cpp`、`camera_napi.cpp`、`cs30_sensor_adapter.cpp`、`harmony_usb_transport.cpp`，并链接更新后的核心；Node 头文件适配方法见 `tools/napi_host_test.js` 开头。Node >=22.13 可运行：

```bash
node apps/harmony/tools/camera_host_test.js /absolute/path/entry.node .
```

为覆盖鸿蒙 NAPI 的长度差异，主机插件另编一份：把普通 Node shim 的 include 路径换为 `apps/harmony/tools/ohos_napi_shim`，加 `-D__OHOS__`，输出为 `entry-ohos.node`。对它运行同一 `camera_host_test.js` 和 `napi_host_test.js`；测试专用 shim 让 Node 返回鸿蒙的 TypedArray 字节数语义，包含非零偏移和视图周围负数的越界回归。该 shim 只用于主机测试。

## 界面

- 连接按钮请求深度和彩色；重启按钮停止后重新开流，断开按钮取消并排空请求后释放连接。
- 9×6 栅格按行显示（· 空、■ 障碍、? 未知），每行有读屏文字（accessibilityText）。
- 彩色和深度预览来自同组真实采集帧，最多每秒更新 5 次；彩色异步解码，深度按 0.1–5 m 显示为近亮远暗、无效黑色。后台暂停预览，停止与重连会清除旧画面。
- 栅格主状态独立显示，地面诊断的具体比例每秒更新；地面拟合失败时仍全部为未知，没有放宽拟合条件。
- 没连设备显示“未连接”，拿不到的值不显示；帧率只在开流后用实测帧数算。
- 状态 2 的触点表示（平 / 凸）待 Hsinlung 定：配置里没设定时不预选，必须手选才能发帧。
- “持续发送”“后台运行”配合真机清单第 4 条；普通手机没有通用 USB 相机保活资格，长时任务申请成功也需要实际息屏测试。
- “平面检查”在界面线程上同步计算（建 4 张查表），平板上可能卡一两秒。

2026-11-18 用户在修复 NAPI 长度单位后确认相机连接与收帧正常，随后反馈页面没有预览、地面诊断约 40% 的点低于拟合平面超过 10 cm。当前补齐上述预览并拆分主状态与诊断；相机离地约 1 m、朝前。实际地面拟合失败的原因仍需保存真实深度帧和平面检查，不能把界面修改视为算法验证通过。

预览控制器回归：`node apps/harmony/tools/preview_host_test.js .`（从仓库根运行）。覆盖异步解码限流、同帧去重、断开重连和切到后台时丢弃旧结果、单路解码失败及资源释放。2026-11-19 扩展为两路分别注入解码卡住、ImageSource/PixelMap 释放卡住、丢失显示回调，以及 9000 帧（按 5 次/秒为 30 分钟）的虚拟时间循环，检查另一通道继续、资源数量有界、延迟结果丢弃和后续恢复；这是模拟测试，不是真机 30 分钟验证。采集联调另验证按需求复制、原始帧进度与预览进度分离、通道选择、槽位描述复用，以及已有有效帧后停顿时的超时诊断。

该预览版已通过标准 Node 与模拟鸿蒙字节数语义两套采集/NAPI 回归、预览控制器回归及 DevEco 签名 HAP 构建；已在上述平板覆盖安装并启动，截图确认双预览区域正常显示。安装验证时平板接电脑，相机未连接，真实图像显示与地面拟合仍待接回相机实测。

2026-11-19 长时运行优化：彩色/深度不再串行等待，SDK 操作超时会明确提示并限制任务数量；显示回调缺失时有界重置。原生图像改为按预览需求复制，USB 描述复用，诊断和页面刷新降频；前后台暂停的是预览与页面轮询。新增采集、预览进度和刷新延迟。用户确认旧版约 10 分钟后双画面停止，无发热或切后台；本轮平板不在用户身边，新版尚未覆盖安装，真实长时效果待复测。

该优化版已通过预览控制器扩展模拟、标准 Node 与模拟鸿蒙字节数语义的采集/NAPI 两套回归，以及 DevEco 原生、ArkTS 和签名 HAP 构建。签名包保存在工程默认输出，另复制到本机桌面 `LingTouch-Harmony-20261119.hap`；验证记录和摘要在忽略的 `.build/camera-tools/harmony-performance-verification.json`。下一步在同一平板通过 DevEco/HDC 覆盖安装，完成前台至少 30 分钟及原有后台测试。

2026-11-20 长时运行优化（`core/include/lingtouch/modules.h` 和全部 `SensorAdapter` 方法保持不变）：

- USB 回调仅校验包描述并复制小批次；原生固定 32 槽缓冲池由单独线程按到达顺序拼帧、交付算法。队列溢出会报告中断并走现有恢复流程，不继续解析缺包数据；诊断显示队列深度、峰值和溢出数。相机分辨率、输入帧率和每请求最多 8 包保持原设置。
- 取消接收最多等待 3 秒，超时返回错误，保留仍被系统占用的槽位和缓冲；命令队列可继续处理后续重试。真正排空前禁止重开、切换接口或释放连接。重启操作会重新打开 USB 连接。系统一直不完成取消时仍可能需要插拔或重启应用，不能强行释放在途内存。
- 相机控制使用独立原生线程，通过 TSFN 返回结果，避免停止或重连排在卡住的 ImageKit 共享线程池任务之后；同一时刻仍只允许一个控制操作。
- 每路预览最多保留一组旧的未完成任务，并允许一组替换任务继续显示。旧任务的忙状态与资源所有权保留，迟到结果释放后丢弃；旧任务与替换任务同时卡住时停止继续创建，避免无限分配。页面刷新不再等待图像 SDK Promise 完成。
- 算法复用积分图、掩膜和内点缓冲，先用相同顺序的采样点拟合地面，再在成功时直接生成地面点云，省去整幅中间相机点云。RANSAC 所有点均为内点时提前结束，保持首次最优平面和原有判定规则。
- 默认对实时原生目标启用 `-O2`，调试部署保留符号及严格浮点设置；需要逐行排查时可通过 CMake `-DLINGTOUCH_HARMONY_OPTIMIZE=OFF` 关闭此项。

验证包括核心 14 项测试、优化前后参考帧/合成场景结果对比、标准 Node 和模拟鸿蒙字节数语义的真实采集链联调、预览的有界任务替换与虚拟长时循环。另用 `tools/control_pool_host_test.js`（运行前设置 `UV_THREADPOOL_SIZE=1`）验证相机控制不受共享工作线程占用影响。模拟取消回调缺失后返回超时且不释放缓冲，补齐回调后重连成功。以上不能代替平板长时实测。
