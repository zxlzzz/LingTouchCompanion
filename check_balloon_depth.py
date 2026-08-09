#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
直接在 metric 深度 .npy 上读气球所在像素区域 vs 紧邻背景区域的深度值,
不用高度窗口启发式——气球是躺在地上的长条气球,不是悬挂物,原来的
"离地1.0-2.2m"假设从一开始就是错的。

像素框是在原图(3072x4096)上人工量出来的(见对话里的网格截图), 单位: (x0,y0,x1,y1)。
"""

import numpy as np

CASES = [
    dict(label="balloon_1m_2m / 近气球(标称1m)",
         depth="pics/depth_out/balloon_1m_2m_raw_depth_meter.npy",
         obj=(150, 2780, 450, 2870), bg=(150, 2620, 450, 2720)),
    dict(label="balloon_1m_2m / 远气球(标称2m)",
         depth="pics/depth_out/balloon_1m_2m_raw_depth_meter.npy",
         obj=(2650, 1995, 2950, 2060), bg=(2650, 2100, 2950, 2180)),
    dict(label="balloon_1m_chair_3m / 气球(标称1m)",
         depth="pics/depth_out/balloon_1m_chair_3m_raw_depth_meter.npy",
         obj=(150, 3010, 450, 3090), bg=(150, 2700, 450, 2850)),
    # 2026-08-09 补拍: 无黑布普通地面对照组, bbox 用颜色阈值(R>G+15 & B>G+5)在原图上定位气球像素后人工核实。
    # 场地并非纯素地面, 是浅蓝色环氧地坪(左侧)+深色胶垫(右侧/近处), 气球躺在浅蓝地坪上但延伸到深色胶垫,
    # 特意把框收在 x<2050 (确认全程浅蓝地坪, 见现场照片) 避开材质交界处的混淆。
    dict(label="balloon_1m_plain / 气球(标称1m, 浅蓝地坪)",
         depth="pics/depth_out/balloon_1m_plain_raw_depth_meter.npy",
         obj=(1750, 2226, 2050, 2261), bg=(1750, 2320, 2050, 2380)),
]


def stats(depth, box):
    x0, y0, x1, y1 = box
    patch = depth[y0:y1, x0:x1]
    return dict(mean=float(np.mean(patch)), median=float(np.median(patch)),
                std=float(np.std(patch)), n=patch.size)


def main():
    print(f"{'场景':<32}{'气球区均值':>10}{'气球区中位':>10}{'背景均值':>10}{'背景中位':>10}"
          f"{'差(m)':>8}{'差%':>8}")
    for c in CASES:
        depth = np.load(c["depth"]).astype(np.float32)
        so = stats(depth, c["obj"])
        sb = stats(depth, c["bg"])
        diff = so["median"] - sb["median"]
        diff_pct = diff / sb["median"] * 100
        flag = "  <-- 气球在深度图里可辨认(比背景近)" if diff < -0.03 else \
               "  <-- 深度图里看不出气球(和背景几乎一样)"
        print(f"{c['label']:<32}{so['mean']:>10.3f}{so['median']:>10.3f}"
              f"{sb['mean']:>10.3f}{sb['median']:>10.3f}{diff:>8.3f}{diff_pct:>8.1f}{flag}")


if __name__ == "__main__":
    main()
