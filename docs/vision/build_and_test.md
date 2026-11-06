# 构建与测试

所有命令从仓库根目录执行。正常构建不依赖原工作区、预先生成的 `.runtime`、模型权重或大数据集。

## 环境

| 用途 | 依赖 |
|---|---|
| 安卓 APK | JDK 17、SDK 36、NDK 27.2.12479018（r27c）、CMake 3.22.1+、Gradle 8.14.3 |
| 便捷工具 | Python 3.10+，脚本本身只用标准库 |
| 完整主机回归 | C++17 编译器、CMake、Ninja；Python 3.12 + NumPy 1.26.4 用于既有旧板向量生成核对 |
| 安卓自动回归 | 上述安卓工具，加运行中的 x86_64 模拟器或 ARM64 Android 设备；测试本身模拟 USB |
| 可选 RGB-D 原型 | 单独的 Python 3.12 环境及该目录 requirements；模型已附在 `models/segformer-b0-ade`，不影响当前 APK |

首次 Gradle 构建需要联网获取工具/依赖；交付不带缓存。已有 Gradle 8.14.3 缓存时可用 `--offline`，便捷工具会优先使用现有发行版，避免 wrapper 再下载。安装环境命令按各自平台执行，项目不自动安装驱动。

## 标准 Android Studio

打开 `apps/android-cs30-live`，配置 SDK/NDK/CMake，同步并构建。命令行为：

```shell
cd apps/android-cs30-live
gradlew.bat :app:assembleDebug
```

Linux/macOS 使用 `./gradlew`。产物为 `app/build/outputs/apk/debug/app-debug.apk`。原生代码由 Gradle 直接从仓库 `core` 与 `perception/native` 构建。

## 命令行便捷入口

设置 `ANDROID_HOME`、`JAVA_HOME` 后：

```shell
python perception/tools/vision.py build
```

独立 NDK/CMake 或非标准安装可显式指定，路径用实际环境替换：

```shell
python perception/tools/vision.py configure --sdk "SDK目录" --ndk "NDK目录" --java-home "JDK17目录" --cmake "cmake可执行文件" --ninja "ninja可执行文件"
python perception/tools/vision.py build --offline
```

参数保存到应用的 `local.properties`，被 Git 忽略。使用外部 CMake 且 Ninja 不在同一 bin 目录时，便捷工具会将 Ninja 加入本次构建的 PATH；Android Studio 也需能找到它，或直接使用 SDK Manager 安装的配套 CMake/Ninja。

## 主机核心回归

```shell
python perception/tools/host_test.py --cmake "cmake可执行文件" --ninja "ninja可执行文件"
```

Windows 自动探测 Visual Studio Build Tools；也可先打开其开发者命令行。Linux/macOS 用系统 C++ 编译器。脚本将所选 Python 传给 CMake，避免生成器误用另一套无 NumPy 的 Python。

覆盖旧板编码、参数、启动表、标定、拼帧、几何、参考原生帧、工作线程，以及旧入口连续处理/新入口手动自动的兼容性。

## 安卓交互回归

先启动模拟器（本次使用 Android 34 x86_64、3 GB 内存、2 核），再运行：

```shell
python perception/tools/vision.py test --serial emulator-5554 --offline
```

工具解压最小夹具到 `.build/vision/test-assets`、核对 SHA-256、单独编译模拟 USB 测试库、构建两个 APK 并安装到指定设备。默认测试 ABI 为 x86_64；ARM64 使用 `--test-abi arm64-v8a --serial 实际序列号`。在真实手机执行此命令仍然是模拟 USB 测试，不等于相机接线验收。

测试结果、截图、导出的 JSON/诊断在 `.build/vision/test-results`；不进入交付源码。`--publish` 仅在成功完成测试后将本次 APK 复制到 `deliverables/vision/android` 并更新校验值。

生产 APK 不含模拟库、测试数据或模型权重。正式签名由团队配置；不交付个人签名密钥。旧 `apps/android`、原生 `apps/harmony` 各自的完整平台构建另按原 README；本次当前主入口是 `android-cs30-live`。
