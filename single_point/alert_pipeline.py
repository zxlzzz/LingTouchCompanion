#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
single_point/alert_pipeline — 核心: metric 深度 -> 单点障碍告警 (bool | None)

对照条件说明见仓库根目录 1.md。目的: 与 visionss/(spatial grid，10x9栅格给方位) 做
RQ1 对比——同一相机、同一深度模型(Depth-Anything-V2 metric-hypersim-vitl)、同一相机
标定(fx=3260px)、同一地面拟合算法，只把"深度图怎么变成输出"从"俯视栅格"换成"身前
一个矩形区域内有没有东西"。隔离的自变量是"空间信息的价值"，所以除了这一步，其余全部
直接复用 visionss/topdown_pipeline 的函数，不复制一份。

检测区域 (胸挂佩戴, 与 visionss 同一套标定):
  前向  0.5 ~ 2.5 m   —— 白杖近场之外、一步可达的距离
  侧向  ±0.35 m       —— 70cm 身宽稍大，只关心正前方会撞到的
  高度  0.10 ~ 1.80 m —— 剔地板/天花板，与 visionss/topdown_pipeline.py 一致(直接复用其常量)

用法:
  from alert_pipeline import depth_to_alert
  result = depth_to_alert(depth, fx=3260.0)
  if result is None:
      ... 本帧地面拟合失败, 不下发 ...
  else:
      obstacle, count, threshold = result
"""

import os
import sys

import numpy as np

# 直接 import visionss/topdown_pipeline 里已经写好、验证过的地面拟合，不重写一份。
_VISIONSS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "visionss")
if _VISIONSS_DIR not in sys.path:
    sys.path.insert(0, _VISIONSS_DIR)

from topdown_pipeline import (  # noqa: E402
    backproject, ransac_ground, matvec, ground_frame,
    STRIDE, H_MIN, H_MAX, CAM_H_TRUE,
)

# ── 检测区域参数 ─────────────────────────────────────
D_FWD_MIN, D_FWD_MAX = 0.5, 2.5   # 前向检测范围(m)
LAT_HALF_WIDTH = 0.35              # 侧向半宽(m)，总宽 0.70m
# 占据阈值: 与 visionss/topdown_pipeline.py 的 occupancy() 同一思路——阈值按比例算
# (该矩形区域"完全被障碍物填满时应有的点数" × OCC_FILL_FRAC)，不用绝对点数，这样
# 手机实拍分辨率跟标定分辨率不一致时阈值能跟着自动缩放，不会整体失效。
OCC_FILL_FRAC = 0.035
OCC_MIN = 8
# ────────────────────────────────────────────────────


def depth_to_alert(depth, fx, fy=None, cam_h_true=CAM_H_TRUE, stride=STRIDE):
    """metric 深度图 -> 身前矩形区域是否有障碍。

    地面拟合(两遍、带 scale 尺度锚定)与 visionss/topdown_pipeline.depth_to_grid()
    完全一致，唯一差异是最后一步不做 10x9 俯视分箱，而是直接数"检测矩形内存活点数"。

    返回:
      (obstacle: bool, count: int, threshold: int)  正常一帧
      None                                            地面拟合失败(画面底部没拍到地板等)，
                                                        本帧作废，调用方不应下发
    """
    depth = np.asarray(depth, dtype=np.float32)
    H, W = depth.shape
    cx, cy = W / 2, H / 2
    fy = fx if fy is None else fy
    rng = np.random.default_rng(0)

    try:
        pts, vs = backproject(depth, fx, fy, cx, cy, stride)
        _, _, cam_h_raw, _, _ = ransac_ground(pts, vs, H, rng)
        scale = cam_h_true / cam_h_raw
        pts, vs = backproject(depth * scale, fx, fy, cx, cy, stride)
        n, d, _, _, _ = ransac_ground(pts, vs, H, rng)
    except RuntimeError as e:
        print(f"[alert_pipeline] 地面拟合失败, 本帧作废(不下发): {e}")
        return None

    h_pts = matvec(pts, n) + d
    fwd, right = ground_frame(n, pts)
    d_fwd = matvec(pts, fwd)
    d_lat = matvec(pts, right)

    keep = ((h_pts > H_MIN) & (h_pts < H_MAX)
            & (d_fwd > D_FWD_MIN) & (d_fwd < D_FWD_MAX)
            & (np.abs(d_lat) < LAT_HALF_WIDTH))
    count = int(np.count_nonzero(keep))

    # 检测区域在标定分辨率下、被完全填满时的预期点数(下采样后)。
    z_mid = (D_FWD_MIN + D_FWD_MAX) / 2.0
    expected = ((2 * LAT_HALF_WIDTH) * fx / z_mid) * ((H_MAX - H_MIN) * fy / z_mid) / (stride ** 2)
    threshold = max(int(expected * OCC_FILL_FRAC), OCC_MIN)

    return count >= threshold, count, threshold


def _main():
    """离线自检: 灌一张 .npy 深度图, 打印告警结果。不做可视化(这台机器 lingtouch 环境
    matplotlib savefig 会崩, 见根目录 CLAUDE.md; 数值验证不需要图)。"""
    import argparse
    from PIL import Image

    ap = argparse.ArgumentParser()
    ap.add_argument("--depth", required=True, help=".npy 米制深度图")
    ap.add_argument("--img", help="原图(仅用于核对深度图尺寸, 可省略)")
    ap.add_argument("--fx", type=float)
    ap.add_argument("--calib", type=str, help='"PX REAL DIST"')
    args = ap.parse_args()

    depth = np.load(args.depth).astype(np.float32)
    if args.img:
        img = np.array(Image.open(args.img))
        if depth.shape[:2] != img.shape[:2]:
            depth = np.array(Image.fromarray(depth).resize(
                (img.shape[1], img.shape[0]), Image.BILINEAR))

    if args.calib:
        px, real, dist = map(float, args.calib.split())
        fx = px * dist / real
        print(f"[标定] fx = {px:.0f}px x {dist}m / {real}m = {fx:.1f}px")
    elif args.fx:
        fx = args.fx
    else:
        raise SystemExit("需要 --fx 或 --calib")

    result = depth_to_alert(depth, fx=fx)
    if result is None:
        print("[alert] 地面拟合失败")
        return
    obstacle, count, threshold = result
    print(f"[alert] {'障碍 ■' if obstacle else '通畅 □'}  "
          f"(存活点数 {count} / 阈值 {threshold})")


if __name__ == "__main__":
    _main()
