#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_distance — 用标定出的 fx 批量跑测试集, 对比模型估的物体距离 vs 卷尺量的真实距离。

流程:
  1. 原始深度 backproject → 两轮地面拟合(RANSAC + 剔除>8cm残差再精修) → 得到未锚定的相机高度 cam_h_raw
  2. 尺度锚定: scale = CAM_H_TRUE / cam_h_raw, 深度整体乘 scale
  3. 用缩放后的深度重新 backproject + 两轮地面拟合(理论上此时 cam_h ≈ CAM_H_TRUE, 当交叉验证用)
  4. 高度过滤 + 前向距离估计(中心 ±0.6m 内最近5百分位)

复用 visionss/topdown_pipeline.py 的 backproject / ransac_ground / ground_frame / matvec。
"""

import sys
from pathlib import Path

import numpy as np
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent / "visionss"))
from topdown_pipeline import backproject, ransac_ground, ground_frame, matvec

FX = 3260.0        # 用户复测: 门扇1467px(3072宽基准) * 2.0m / 0.90m
STRIDE = 8
CAM_H_TRUE = 1.40  # 胸挂实测高度(m) —— 尺度锚定基准

# (图片, depth npy, 真实距离(m) 或 None, 说明)
CASES = [
    ("pics/ascii/empty1.jpg",   "pics/depth_out/empty1_raw_depth_meter.npy",   None, "空场1"),
    ("pics/ascii/empty2.jpg",   "pics/depth_out/empty2_raw_depth_meter.npy",   None, "空场2"),
    ("pics/ascii/chair_2m.jpg", "pics/depth_out/chair_2m_raw_depth_meter.npy", 2.0,  "椅子2m"),
    ("pics/ascii/chair_3m.jpg", "pics/depth_out/chair_3m_raw_depth_meter.npy", 3.0,  "椅子3m"),
    ("pics/ascii/chair_4m.jpg", "pics/depth_out/chair_4m_raw_depth_meter.npy", 4.0,  "椅子4m"),
    ("pics/ascii/chair_5m.jpg", "pics/depth_out/chair_5m_raw_depth_meter.npy", 5.0,  "椅子5m"),
    # 2026-08-09 补拍: 无黑布普通地面对照组 (相机高度同样约1.4m)
    ("pics/ascii/empty3.jpg",         "pics/depth_out/empty3_raw_depth_meter.npy",         None, "空场(普通地面)"),
    ("pics/ascii/chair_3m_plain.jpg", "pics/depth_out/chair_3m_plain_raw_depth_meter.npy", 3.0,  "椅子3m(普通地面)"),
]

H_MIN, H_MAX = 0.15, 1.0     # 椅子高度过滤窗口(m, 离地)
LAT_HALF_WIDTH = 0.6          # 只看画面正前方 ±0.6m 的点
NEAR_PCTL = 5                 # 该窗口内最近的第5百分位深度 = 物体前表面距离


def fit_ground(depth, img_shape):
    H, W = depth.shape
    cx, cy = W / 2, H / 2
    pts, vs = backproject(depth, FX, FX, cx, cy, STRIDE)
    rng = np.random.default_rng(0)
    n, d, cam_h, pitch, inlier_frac = ransac_ground(pts, vs, H, rng)
    return pts, n, d, cam_h, pitch, inlier_frac


def analyze(img_path, depth_path, true_dist, label):
    img = np.array(Image.open(img_path))
    depth_raw = np.load(depth_path).astype(np.float32)
    if depth_raw.shape[:2] != img.shape[:2]:
        depth_raw = np.array(Image.fromarray(depth_raw).resize(
            (img.shape[1], img.shape[0]), Image.BILINEAR))

    # 第一遍: 原始深度, 只为拿 cam_h_raw 算 scale
    _, _, _, cam_h_raw, _, _ = fit_ground(depth_raw, img.shape)
    scale = CAM_H_TRUE / cam_h_raw
    depth_scaled = depth_raw * scale

    # 第二遍: 缩放后的深度重新走一遍完整流程(交叉验证 cam_h≈CAM_H_TRUE)
    pts, n, d, cam_h, pitch, inlier_frac = fit_ground(depth_scaled, img.shape)

    h_pts = matvec(pts, n) + d
    fwd, right = ground_frame(n, pts)
    d_fwd = matvec(pts, fwd)
    d_lat = matvec(pts, right)

    mask = (h_pts > H_MIN) & (h_pts < H_MAX) & (np.abs(d_lat) < LAT_HALF_WIDTH)
    n_pts = int(mask.sum())
    est = float(np.percentile(d_fwd[mask], NEAR_PCTL)) if n_pts >= 30 else None

    err = err_pct = None
    if est is not None and true_dist is not None:
        err = est - true_dist
        err_pct = err / true_dist * 100

    return dict(label=label, cam_h_raw=cam_h_raw, scale=scale, cam_h=cam_h, pitch=pitch,
                inlier=inlier_frac, n_pts=n_pts, est=est, true=true_dist, err=err, err_pct=err_pct)


def main():
    rows = [analyze(*c) for c in CASES]

    print(f"{'场景':<12}{'cam_h_raw':>10}{'scale':>8}{'cam_h(锚定后)':>13}{'俯仰':>8}"
          f"{'内点率':>8}{'窗口点数':>8}{'估距':>8}{'真实':>8}{'误差':>8}{'误差%':>8}")
    for r in rows:
        est_s = f"{r['est']:.2f}" if r['est'] is not None else "n/a"
        true_s = f"{r['true']:.2f}" if r['true'] is not None else "--"
        err_s = f"{r['err']:+.2f}" if r['err'] is not None else "--"
        errp_s = f"{r['err_pct']:+.1f}" if r['err_pct'] is not None else "--"
        flag = "" if abs(r['cam_h'] - CAM_H_TRUE) < 0.02 else "  <-- 锚定后仍偏! 检查地面拟合"
        print(f"{r['label']:<12}{r['cam_h_raw']:>10.2f}{r['scale']:>8.3f}{r['cam_h']:>13.3f}"
              f"{r['pitch']:>8.1f}{r['inlier']:>8.0%}{r['n_pts']:>8d}"
              f"{est_s:>8}{true_s:>8}{err_s:>8}{errp_s:>8}{flag}")

    # ── 健康指标: 同一个地面场景下, scale 的离散度理论上应该很小(<10%)。
    # 离散度大 → 说明不同帧的地面拟合互相不一致(比如被不同程度的物体污染),
    # 尺度锚定只是治标, 真正该看这个数——这批照片全是同一块黑布地面, 一起统计。
    scales = np.array([r["scale"] for r in rows])
    cv = scales.std() / scales.mean()
    print(f"\n[健康指标] scale: mean={scales.mean():.3f}  std={scales.std():.3f}  "
          f"CV(离散度)={cv:.1%}  {'✓ 干净(<10%)' if cv < 0.10 else '✗ 超标(>=10%), 地面拟合不一致'}")


if __name__ == "__main__":
    main()
