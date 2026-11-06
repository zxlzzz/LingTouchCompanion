# 离线参考实验

[rgbd_offline](rgbd_offline/README.md) 是可选的 RGB-D 地面先验/栅格网页原型，使用本目录之外、perception 内的 `models/segformer-b0-ade`。不作为实时 APK 的执行入口。

当前实时深度实现见 [vision/native](../vision/native/README.md)，参数在 `vision/core/config/lingtouch_defaults.conf`。Python 原型与 C++ 核心的参数分别管理；修改原型不会改变 APK。
