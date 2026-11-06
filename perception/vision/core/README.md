# 实时点阵核心

本目录是 `perception/apps/android-cs30-live` 使用的独立 C++17 核心。由 Kotlin/JNI 调用 `lingtouch/engine.h`；不依赖仓库根目录 `core` 或 `agent`，不改变团队旧外壳。

| 位置 | 内容 |
|---|---|
| `include/lingtouch/engine.h` | 启动响应、收包、工作线程、手动/自动门控与快照 |
| `src/depth_evidence.cpp` | 10 cm 小格证据、40 cm 大格聚合及 K 阈值点阵 |
| `include/lingtouch/types.h` | 深度、地面、0/1/2 栅格及小格证据 |
| `config/lingtouch_defaults.conf` | 编译时嵌入的默认参数 |
| `src/tactile_legacy.cpp` | 原有 15 字节手柄编码兼容入口，未改为 K 编码 |
| `tests`、`tools` | 旧板编码与参数回归、向量生成器 |

感知算法与 USB 实现在 [../native](../native/README.md)。完整流程见 [pipeline.md](../../docs/vision/pipeline.md)。

从 perception 目录运行：

```shell
python tools/host_test.py --cmake "cmake可执行文件" --ninja "ninja可执行文件"
```

需 C++17/CMake；生成器核对还需 Python 和 NumPy。编码参考已随模块放在 [tests/reference](../../tests/reference/README.md)，不再读取根目录 experiments。向量有效行保持不变。

`Engine(config)` 保持连续处理入口，实时 App 用 `Engine(config, true)` 默认暂停。旧 0/1/2 编码与新 K 点阵并行；未知区域不代表可通行。编译禁止 fast-math/FMA 合并，维持测试中的确定性。
