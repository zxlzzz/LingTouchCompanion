# 离线参考实验

[rgbd_offline](rgbd_offline/README.md) 是可选的 RGB-D 地面先验/栅格网页原型，使用本目录之外、perception 内的 `models/segformer-b0-ade`。不作为实时 APK 的执行入口。

实时深度实现见 [native](../native/README.md)，参数在 `core/` 的统一配置。Python 原型与 C++ 核心的参数分别管理，改原型不影响 App。
