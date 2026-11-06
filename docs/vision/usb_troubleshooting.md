# USB 与供电排障

## 已确认的现场条件

手机连接 CS30 曾在 `startup step 38: LIBUSB_ERROR_IO (-1)` 失败。用户给扩展坞 PD 口接充电宝后可用。因此本次演示复用该外接供电方案，不依赖未经核验的手机直供电能力。

第 38 步是 UVC Commit，尚未进入等时深度接收。IO 是通用传输失败，不是专门的供电错误；其他设备组合仍可能涉及线材、OTG、系统驱动或协商。手机型号、扩展坞和充电宝型号尚未记录。

## 按提示定位

| 提示/现象 | 含义与处理 |
|---|---|
| 首次未发现 USB 设备 | 确认手机主机/OTG、数据线、扩展坞数据口与 PD 外供电，点刷新 |
| 未授予 CAMERA/USB 权限 | 允许后重试；CAMERA 是 Android 对 UVC USB 访问的授权要求，不据此认定系统相机在占用 |
| Java force claim 失败 | 日志有接口号和接管前驱动状态；停止其他正在使用相机的应用，再重新连接 |
| native claim BUSY | 确认平台先 force claim、native auto-detach=0；检查是否仍有旧清理任务 |
| Commit step 38 IO | 先复用已验证的 PD 外供电和数据连接；仍失败则保留日志，核对控制传输/手机兼容性 |
| 枚举缺失/查询异常 | 1.2 只记录发现状态，不直接关闭当前连接或清除授权请求 |
| NO_DEVICE / USB 流停止 | 底层传输报告失效；确认供电/线缆、重新选择设备连接，并导出日志 |
| 5 秒没有新结果 | 采集暂停并保持最后结果；检查是否收到 USB 包，不能重用旧帧伪装新采集 |
| 当前帧无地面参考 | 连接可能正常，属于几何处理条件不足；不是 USB 断开。斜向下观察有地面的有效量程场景再验收 |

## 接管与生命周期约定

Java 按接口 ID 去重并 force claim，然后 native 在同一内核打开文件描述上登记 claim，关闭自动 detach。native 持有 dup，Java 不在异步传输排空前释放接口。已提交的传输由回调完成/取消后才释放；超时保留设备、上下文、缓冲和事件泵，后台清理结束前拒绝重开。

复位后的旧 claim 不能直接复用，必须重新经过平台侧 force claim。整理时保留团队的设备速度/配置及 libusb 告警诊断，避免用一个进程全局回调覆盖另一个连接的日志；每个 context 独立登记并随退出移除。

导出日志记录系统 USB 事件、枚举列表状态、Java force claim、native claim 策略、GETDRIVER 名称/errno、最近回调及错误状态。驱动名 `usbfs` 不足以识别具体占用进程。`libusb_kernel_driver_active()` 仅给状态，驱动名称另用 GETDRIVER 查询。

参考：[CS30 供电规格](https://support.tofsensors.com/product/CS30.html)、[Android UsbManager](https://developer.android.com/reference/android/hardware/usb/UsbManager)、[libusb 异步取消约定](https://libusb.sourceforge.io/api-1.0/group__libusb__asyncio.html)。本地的 `perception/cs30/REPORT.md` 保留协议来源；历史“手机未测试”结论应结合本目录的新反馈阅读。
