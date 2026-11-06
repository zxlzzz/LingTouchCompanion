# 视觉工具

| 入口 | 用途 |
|---|---|
| `vision.py configure/build/test` | 本机设置、标准 Gradle 构建、模拟器交互回归 |
| `host_test.py` | 完整 C++ 核心回归，含旧入口与受控采集兼容性 |
| `cs30_pc_probe/run.py` | Windows 真实相机两轮连接/收帧/停止/重开检查 |

构建环境见 [build_and_test.md](../../docs/vision/build_and_test.md)。全部生成文件写入 `.build/vision`，不进入源码。PC 工具只在显式运行时访问相机，不自动安装或替换驱动。

Windows 本机需要已经可访问的 CS30/libusbK 或 WinUSB。外部 libusb DLL 可来自使用者自行安装的 [libusb-package](https://pypi.org/project/libusb-package/)；本交付不带 DLL 或厂商 SDK。示例：

```shell
python perception/tools/cs30_pc_probe/run.py --usb-dll "libusb-1.0.dll的完整路径" --cmake "cmake可执行文件" --ninja "ninja可执行文件"
```

`--compile-only` 仅检查编译，不打开相机。正常执行保存两张原生深度样本及紧凑检查结果到 `.build/vision/pc-probe/capture`。该测试不评价障碍检测准确率，也不能替代手机端 USB 验收。
