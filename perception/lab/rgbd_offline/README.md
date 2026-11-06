# 可选：离线 RGB-D 参考实现

该目录保留已验证的 RGB 地面先验原型，供以后补 RGB 取流/配准时参考。当前实时 APK 只用原生深度，不依赖这里、PyTorch 或模型权重。

输入：同帧 960×540 `RGBD_RGB[n].png` 与 uint16 小端毫米 `RGBD_Depth[n].raw`，RAW 必须为 1,036,800 字节。沿用当时 RGB 近似内参、光轴 Z、无额外去畸变假设；不能输入 640×480 原生深度来冒充该格式。

参考环境为 Python 3.12；与只用标准库的安卓构建工具分开安装。

```shell
python -m venv .venv
python -m pip install -r requirements.txt
python cs30_web.py --model-dir ../../models/segformer-b0-ade --open
```

在当前目录执行，使用所建虚拟环境的 Python。所需模型位于 perception 下的 `models/segformer-b0-ade`，包含配置、预处理配置与权重；来源、许可及校验见 [模型说明](../../models/segformer-b0-ade/README.md)。程序只读取本地权重，不自动下载数据或模型。

网页地址默认 `http://127.0.0.1:8765`，上传 RGB/RAW 后处理；K 变化在浏览器中重算点阵。`geometry.py` 是基础几何，`spatial_grid.py` 是细格/粗格计数，`rgbd_floor_demo.py` 包含地面先验和拟合。历史报告生成函数为复核保留，不是手机生产入口。

```shell
python -m unittest test_geometry test_spatial_grid test_rgbd_floor
```

以上是几何/未知状态回归，不需要模型文件，但模块导入需要安装依赖。与 C++ 主线的去噪和 RANSAC 抽样策略有差别，不能把两者的结果差异只归因于是否使用 RGB。当前原生深度主线说明见 [pipeline.md](../../docs/vision/pipeline.md)。
