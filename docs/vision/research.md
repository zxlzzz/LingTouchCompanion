# 研究选型摘要

整理自 2026-11-02 至 11-04 的已有调研与实验。这里是后续参考，不是当前 APK 的运行依赖，也没有声称已复现下列完整系统。

## 值得读的系统

| 系统/实现 | 可借鉴内容 | 当前接入前提 |
|---|---|---|
| [WOAD](https://github.com/MMCNJUPT/WOAD) | 同款 CS30 的采集、检测、手机及反馈分工 | 先核对模态和预处理；不是拿现成权重就等于重建整机 |
| [RTAB-Map](https://github.com/introlab/rtabmap) | RGB-D 里程计、回环和地图；CPU 路线 | 需要同步 RGB-D，限制局部地图范围 |
| [Wavemap](https://github.com/ethz-asl/wavemap) | 深度/位姿到多分辨率占用，观测与未知分离 | 必须先有可靠位姿，不能代替 SLAM |
| [PanopticNDT](https://github.com/TUI-NICR/panoptic-mapping) | RGB-D 分割、实例与三维地图融合 | 语义、位姿和更多依赖，优先云端研究 |
| [Unfolding Space](https://github.com/jakobkilian/unfolding-space) | 深度分区如何转成可理解的触觉 | 其图像方向分区不是本项目地面俯视格，需要适配 |
| [ViPlanner](https://github.com/leggedrobotics/viplanner) | 语义/深度到局部路径 | 机器人约束不能直接作为人体和手柄引导约束 |

## 对本项目的取舍

当前为了短期交付，选用传感器实测深度与几何链路，避免固定物体词表限制。无需训练或 GPU。代价是依赖可信地面，无法仅靠本帧解决地面不在视野内、跨帧运动参考或所有近地小障碍。

后续优先分辨失败来源：无有效深度、地面参考失效、噪声、空间栅格门槛、候选漏检分别需要不同处理，不把它们全部归为模型不够大。

若增加 RGB，先完成同步、配准和可见性检查，再用 SegFormer 辅助地面候选；YOLO 原生分割用于对已有测量做实例关联。当前小样本比较没有支持默认增加 SAM；边界分割收益不能修复上游漏检、补造深度或提供地面高度。

历史数值见 [验证记录](validation.md)。公开论文效果、机器人成功率、图像 IoU 与本项目的障碍检出和用户行走表现不是同一指标，不能混成排名。
