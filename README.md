# 灵触·随行 · LingTouch Companion

把视觉信息转换为触觉点阵的辅助感知项目。目标形态：CS30 深度相机（加 IMU）戴在头上、直插手机或平板，所有计算都在手机/平板上，结果编码成点阵经蓝牙发给手柄。点阵 9 列 × 6 行，每格 40 cm（左右 ±1.8 m，前方 1.0–3.4 m）。

## 布局：每个文件夹归谁

| 文件夹 | 归属 | 内容 |
|---|---|---|
| [core/](core/README.md) | 大家共用 | C++17 端侧核心：类型、模块接口、点阵编码、全部参数、给外壳的门面、顶层 CMake |
| [perception/](perception/README.md) | 视觉同学 | `native/` CS30 取流与拆帧、几何、0/1/2；`cs30/` 协议材料；`lab/` Python 实验位 |
| [agent/](agent/README.md) | 对话 agent 同学 | `native/` agent 与语音接口；`backend/` Node.js 导航与命令解析服务 |
| [apps/](apps/README.md) | 交互同学 | `android/`（Kotlin）、`harmony/`（ArkTS，平板优先） |
| [hardware/](hardware/README.md) | Hsinlung | 固件、3D 模型、PCB、头戴方案、BLE 调试页 |
| [experiments/chi2027/](experiments/chi2027/README.md) | Hsinlung | 论文实验通路（手机拍摄 + 电脑深度推理） |
| [docs/](docs/) | — | [方案文档](docs/plans/)、[本次交接](docs/plans/HANDOFF_2026-10-28.md)、[真机验收清单](docs/device_tests.md)、[报告](docs/REPORT_2026-10-28.md)、[本机迁移脚本](docs/migrate_local_2026-10-28.ps1) |
| [archive/](archive/) | — | 不再使用但保留：uni-app 前端、旧 `vision/`、9/29 比赛版 `LingTouch.zip`、10/09 的旧 CLAUDE.md |

## 入口

| 要做的事 | 怎么做 |
|---|---|
| 编译并测试端侧核心 | `cmake -S core -B build/core && cmake --build build/core && ctest --test-dir build/core --output-on-failure` |
| 安卓 App | Android Studio 打开 `apps/android/`（需要 SDK 35、NDK、CMake 3.22.1） |
| 鸿蒙 App | DevEco Studio 打开 `apps/harmony/`（系统 ≥ HarmonyOS 5.1.0 / API 18） |
| 对一帧原始深度打印栅格或做平面检查 | `build/core/perception_tests/lt_frame_tool grid|plane 帧文件 perception/cs30/calibration_0.bin` |
| 论文实验 | `python experiments/chi2027/visionss/phone_server.py`（环境 `D:\anaconda\envs\LING\python.exe`） |
| 导航/命令解析服务 | 进入 `agent/backend/`，`npm ci && npm start` |
| 3D 模型 | 在 `hardware/models/` 下按各模型 README 执行 |
| 真机验收 | [docs/device_tests.md](docs/device_tests.md) |

## 本机数据

模型权重（`Depth-Anything-V2/`）、测试照片（`pics/`）、实验日志（`experiment_runs/`）、`.pcba-workflow/`、建模运行时、密钥、论文材料留在本机，不进 Git。2026-10-28 重构后先运行一次 `docs/migrate_local_2026-10-28.ps1`（只移动、不删除，可加 `-DryRun` 先看），把被忽略的本机文件挪到新位置。
