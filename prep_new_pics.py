#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一次性脚本: 把新拍的3张中文文件名照片复制成ASCII文件名, 放进 pics/ascii/。
不经过命令行参数传中文路径(避免 Git Bash 乱码坑), 直接在 Python 里写路径。
"""
import shutil
from pathlib import Path

PICS = Path("pics")
SRC_DST = [
    (PICS / "空场 n.jpg", PICS / "ascii" / "empty3.jpg"),
    (PICS / "椅子3m n.jpg", PICS / "ascii" / "chair_3m_plain.jpg"),
    (PICS / "气球1m n.jpg", PICS / "ascii" / "balloon_1m_plain.jpg"),
]

for src, dst in SRC_DST:
    assert src.exists(), f"missing: {src}"
    shutil.copy2(src, dst)
    print(f"{src.name} -> {dst}")
