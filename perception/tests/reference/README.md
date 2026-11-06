# 旧板编码参考

`frame_converter.py` 复制自团队仓库 `experiments/chi2027/visionss/frame_converter.py`，来源提交 `d769a6d`。保留原文件，用于独立视觉模块的旧板字节兼容检查；不需要调用根目录 experiments。

`vision/core/tools/gen_legacy_vectors.py` 根据此参考生成冻结向量。源文件按 LF 规范化后核对 SHA-256，避免 Windows 换行造成假变更；此次迁移仅修改向量首行的路径说明，其余期望字节不变。
