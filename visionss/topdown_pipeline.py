#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
灵触随行 — 离线验证管线（metric 深度 → 点云 → 地面拟合 → 高度过滤 → 俯视 10x9 栅格）

输入:
  --img    原始照片 (jpg/png)
  --depth  官方 run.py --save-numpy 输出的 .npy (米制深度, HxW float)
  --fx     焦距(像素)。二选一:
  --calib  "PX REAL DIST"  标定物像素宽 实际宽(m) 拍摄距离(m) → fx = PX*DIST/REAL

用法:
  python topdown_pipeline.py --img 1.jpg --depth 1.npy --calib "1200 0.90 3.0"
  python topdown_pipeline.py --img 1.jpg --depth 1.npy --fx 2300

输出:
  <img名>_topdown.png   四联图: 原图 / 深度 / 俯视点云 / 10x9栅格
  终端打印栅格(每格点数 + 激活图) 便于调阈值

地面拟合(ransac_ground): RANSAC 粗定位平面 → 最小二乘精修 → REFIT_ROUNDS(默认3)轮
非对称迭代剔除(地面以下容忍15cm, 以上只容忍5cm, 专挑椅子腿这类贴地but更高的点甩掉)。
GROUND_IMG_FRAC 从 0.45 收紧到 0.25——45%时近距离物体(椅子)会占满候选带底部, 容易被
误拟合进地面里, 见仓库根目录 TOPDOWN_VALIDATION.md 的详细记录。

已知环境问题: 这台机器(conda env `lingtouch`)的 numpy LAPACK 库整体损坏, 任何
np.linalg.{svd,eigh,inv,det} 调用或大数组 `@`/np.dot 都会静默崩溃(退出码127, 无
traceback)。本文件的地面拟合已经手写绕开(见 matvec/smallest_eigvec_3x3/_det3), 但
main() 末尾用 matplotlib 画四联图那段目前依然会崩(matplotlib 渲染要求逆变换矩阵,
内部调 np.linalg.inv)——批量数值验证请用 validate_distance.py, 不要指望这里的
--outdir 可视化能跑通, 除非先把这个环境的 numpy/BLAS 修好。
"""

import argparse
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image

# ── 可调参数 ─────────────────────────────────────
STRIDE        = 8          # 像素下采样步长(3072x4096 → ~19万点)
H_MIN, H_MAX  = 0.10, 1.80 # 离地高度保留区间(m): 剔地板/天花板
D_MIN, D_MAX  = 0.5, 5.0   # 前向距离区间(m) → 10行
N_ROWS, N_COLS = 10, 9
HFOV_FALLBACK = 67.0       # 无标定时的视场角估计(deg)
# RANSAC
RANSAC_ITERS  = 300
RANSAC_TOL    = 0.05       # 平面内点容差(m)
# 迭代精修(RANSAC之后): 非对称——地面以下(残差为负)容忍到 -15cm(地毯/黑布褶皱),
# 地面以上(残差为正)只容忍 +5cm 就剔除, 专门用来把椅子腿/椅子底这类"贴地但更高"的点甩掉。
REFIT_LOW, REFIT_HIGH = -0.15, 0.05
REFIT_ROUNDS  = 3          # 迭代剔除+精修的轮数(不含 RANSAC 后的第一次精修)
GROUND_IMG_FRAC = 0.25     # 取画面底部这一比例的点做地面候选(45%时椅子距离越近占比越大, 容易把椅子拟合进地面)
GROUND_D_MAX  = 6.0        # 地面候选最远距离(m)
# 占据判定: 每格点数阈值 = OCC_K / z²(近处像素多), 下限 OCC_MIN
OCC_K   = 400.0
OCC_MIN = 8
CAM_H_TRUE = 1.40          # 胸挂实测相机高度(m) —— 尺度锚定基准, 见 TOPDOWN_VALIDATION.md
# ────────────────────────────────────────────────


def backproject(depth, fx, fy, cx, cy, stride):
    H, W = depth.shape
    vs, us = np.mgrid[0:H:stride, 0:W:stride]
    z = depth[vs, us]
    ok = (z > 0.1) & (z < 20) & np.isfinite(z)
    us, vs, z = us[ok], vs[ok], z[ok]
    x = (us - cx) * z / fx
    y = (vs - cy) * z / fy
    return np.stack([x, y, z], axis=1), vs  # 相机系: x右 y下 z前


def matvec(mat, vec):
    """(N,3) @ (3,) 但绕开 BLAS gemv —— 这台机器的 numpy 底层 BLAS/LAPACK 库损坏,
    任何 N≳1000 的矩阵-向量乘法(np.dot/@)或 LAPACK 调用(svd/eigh/det)都会直接把进程打崩
    (无 traceback, 表现为退出码127)。逐元素乘加走 numpy 自己的 SIMD 规约循环, 不经过那个坏库。"""
    return (mat * vec).sum(axis=1)


def _det3(B):
    """3x3 行列式, 手写余子式展开——np.linalg.det 内部也走 LAPACK, 同样会崩。"""
    return (B[0, 0] * (B[1, 1] * B[2, 2] - B[1, 2] * B[2, 1])
            - B[0, 1] * (B[1, 0] * B[2, 2] - B[1, 2] * B[2, 0])
            + B[0, 2] * (B[1, 0] * B[2, 1] - B[1, 1] * B[2, 0]))


def smallest_eigvec_3x3(A):
    """对称 3x3 矩阵最小特征值对应的单位特征向量, Cardano 解析解——不调用 np.linalg.eigh/svd
    (那两个在这台机器上连 3x3 单位阵都会崩, 见 matvec 注释)。"""
    p1 = A[0, 1] ** 2 + A[0, 2] ** 2 + A[1, 2] ** 2
    if p1 < 1e-12:  # 已是对角阵
        diag = np.array([A[0, 0], A[1, 1], A[2, 2]])
        v = np.zeros(3)
        v[np.argmin(diag)] = 1.0
        return v
    q = np.trace(A) / 3.0
    p2 = (A[0, 0] - q) ** 2 + (A[1, 1] - q) ** 2 + (A[2, 2] - q) ** 2 + 2 * p1
    p = np.sqrt(p2 / 6.0)
    B = (1.0 / p) * (A - q * np.eye(3))
    r = np.clip(_det3(B) / 2.0, -1.0, 1.0)
    phi = np.arccos(r) / 3.0
    eig_max = q + 2 * p * np.cos(phi)
    eig_min = q + 2 * p * np.cos(phi + 2 * np.pi / 3)
    M = A - eig_min * np.eye(3)
    best_v, best_norm = None, -1.0
    for i, j in ((0, 1), (0, 2), (1, 2)):  # M 秩<=2, 任取两行叉乘得零空间向量
        v = np.cross(M[i], M[j])
        nn = np.linalg.norm(v)
        if nn > best_norm:
            best_v, best_norm = v, nn
    return best_v / best_norm


def ransac_ground(pts, vs, img_h, rng):
    """底部画面点 RANSAC 拟合地面平面。返回 (unit normal 指向相机侧, d) 使 n·p + d = 0"""
    cand = pts[(vs > img_h * (1 - GROUND_IMG_FRAC)) & (pts[:, 2] < GROUND_D_MAX)]
    if len(cand) < 100:
        raise RuntimeError("地面候选点不足——画面底部没拍到地板?")
    best_n, best_d, best_cnt = None, None, -1
    for _ in range(RANSAC_ITERS):
        i = rng.choice(len(cand), 3, replace=False)
        p0, p1, p2 = cand[i]
        n = np.cross(p1 - p0, p2 - p0)
        nn = np.linalg.norm(n)
        if nn < 1e-9:
            continue
        n = n / nn
        # 地面法线应大致指向相机上方(相机系 y 向下 → 上 ≈ -y)
        if n[1] > 0:
            n = -n
        if -n[1] < 0.7:   # 与竖直夹角>~45°的平面丢弃(墙面)
            continue
        d = -np.dot(n, p0)
        cnt = np.sum(np.abs(matvec(cand, n) + d) < RANSAC_TOL)
        if cnt > best_cnt:
            best_n, best_d, best_cnt = n, d, cnt
    if best_n is None:
        raise RuntimeError("RANSAC 未找到地面平面")

    def _refit(points):
        """3x3 协方差矩阵手动累加(避免大矩阵乘法), 取最小特征值方向作平面法向。"""
        c = points.mean(axis=0)
        dif = points - c
        cov = np.array([[np.sum(dif[:, i] * dif[:, j]) for j in range(3)] for i in range(3)])
        nn = smallest_eigvec_3x3(cov)
        if nn[1] > 0:
            nn = -nn
        dd = -np.dot(nn, c)
        return nn, dd

    # 第一轮: RANSAC 共识内点最小二乘精修
    inl = cand[np.abs(matvec(cand, best_n) + best_d) < RANSAC_TOL]
    n, d = _refit(inl)

    # 后续 REFIT_ROUNDS 轮: 用当前平面重新量全部候选点的带符号残差,
    # 非对称剔除(地面以下容忍15cm, 以上只容忍5cm——专挑椅子腿这类"更高"的点甩), 再精修。
    for _ in range(REFIT_ROUNDS):
        resid = matvec(cand, n) + d
        inl_next = cand[(resid > REFIT_LOW) & (resid < REFIT_HIGH)]
        if len(inl_next) < 50:
            break
        n, d = _refit(inl_next)
        inl = inl_next

    cam_h = abs(d)          # 相机在原点 → 相机离地高度
    pitch = np.degrees(np.arcsin(np.clip(-n[2], -1, 1)))  # 俯仰(相机相对地面)
    return n, d, cam_h, pitch, len(inl) / len(cand)


def ground_frame(n, pts):
    """把点投到地面坐标: forward(相机z在地面上的投影) / lateral / height"""
    up = n
    z_cam = np.array([0.0, 0.0, 1.0])
    fwd = z_cam - np.dot(z_cam, up) * up
    fwd = fwd / np.linalg.norm(fwd)
    right = np.cross(fwd, up)
    right = right / np.linalg.norm(right)
    if right[0] < 0:      # 保证 right 指向相机 x 正方向(画面右)
        right = -right
    return fwd, right


def depth_to_grid(depth, fx, fy=None, cam_h_true=CAM_H_TRUE, stride=STRIDE):
    """metric 深度图 -> 10x9 俯视占据栅格(bool)。供 visionss/phone_server.py 按键回调直接调用。

    与 validate_distance.py 的 analyze() 同一套两遍流程:
      1. 原始深度先拟合一次地面, 拿 cam_h_raw 算 scale = cam_h_true / cam_h_raw
      2. 深度整体乘 scale 后重新 backproject + 拟合地面(此时 cam_h 应回到 cam_h_true 附近)
      3. 高度过滤 + 前向/方位分箱 + OCC_K/z² 占据阈值(与 main() 的 CLI 路径完全一致)

    返回: (10,9) bool ndarray。row 0 = 最近(D_MIN=0.5m), row 9 = 最远(D_MAX=5.0m);
          col 0..8 = 方位角, 左到右(画面左→右, 未做设备穿戴镜像 —— 镜像交给
          frame_converter.mirror_grid_horizontal, 只在打包发给硬件前调用一次)。
    深度不合法(候选点不足/找不到地面)时返回全 False 栅格, 不抛异常——按键回调场景下
    宁可这次不下发/下发空栅格, 也不要让服务端因为一帧糟糕的深度图直接崩掉。
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
    except RuntimeError:
        return np.zeros((N_ROWS, N_COLS), dtype=bool)

    h_pts = matvec(pts, n) + d
    fwd, right = ground_frame(n, pts)
    d_fwd = matvec(pts, fwd)
    d_lat = matvec(pts, right)

    keep = (h_pts > H_MIN) & (h_pts < H_MAX) & (d_fwd > D_MIN) & (d_fwd < D_MAX)
    obs_fwd, obs_lat = d_fwd[keep], d_lat[keep]

    half_fov = np.arctan((W / 2) / fx)
    az = np.arctan2(obs_lat, obs_fwd)
    rows = ((obs_fwd - D_MIN) / (D_MAX - D_MIN) * N_ROWS).astype(int).clip(0, N_ROWS - 1)
    cols = ((az + half_fov) / (2 * half_fov) * N_COLS).astype(int).clip(0, N_COLS - 1)

    counts = np.zeros((N_ROWS, N_COLS), dtype=int)
    np.add.at(counts, (rows, cols), 1)

    row_z = D_MIN + (np.arange(N_ROWS) + 0.5) * (D_MAX - D_MIN) / N_ROWS
    thresh = np.maximum(OCC_K / row_z ** 2, OCC_MIN).astype(int)
    return counts >= thresh[:, None]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--img", required=True)
    ap.add_argument("--depth", required=True)
    ap.add_argument("--fx", type=float)
    ap.add_argument("--calib", type=str, help='"PX REAL DIST"')
    args = ap.parse_args()

    img = np.array(Image.open(args.img))
    depth = np.load(args.depth).astype(np.float32)
    if depth.shape[:2] != img.shape[:2]:
        # run.py 可能缩放过, 深度插值回原图尺寸
        depth = np.array(Image.fromarray(depth).resize(
            (img.shape[1], img.shape[0]), Image.BILINEAR))
    H, W = depth.shape
    cx, cy = W / 2, H / 2

    if args.calib:
        px, real, dist = map(float, args.calib.split())
        fx = px * dist / real
        print(f"[标定] fx = {px:.0f}px × {dist}m / {real}m = {fx:.1f}px")
    elif args.fx:
        fx = args.fx
    else:
        fx = W / (2 * np.tan(np.radians(HFOV_FALLBACK / 2)))
        print(f"[警告] 未标定, 按 HFOV={HFOV_FALLBACK}° 估计 fx={fx:.1f}px")
    fy = fx

    rng = np.random.default_rng(0)
    pts, vs = backproject(depth, fx, fy, cx, cy, STRIDE)
    n, d, cam_h, pitch, inlier_frac = ransac_ground(pts, vs, H, rng)
    print(f"[地面] 相机高度 {cam_h:.2f}m  俯仰 {pitch:+.1f}°  内点率 {inlier_frac:.0%}")
    if not (0.8 < cam_h < 2.0):
        print(f"[警告] 相机高度 {cam_h:.2f}m 不合常理(胸挂应~1.2-1.5m), 地面拟合可能错了")

    # 点离地高度(带符号, 相机侧为正)
    h_pts = matvec(pts, n) + d
    fwd, right = ground_frame(n, pts)
    d_fwd = matvec(pts, fwd)
    d_lat = matvec(pts, right)

    keep = (h_pts > H_MIN) & (h_pts < H_MAX) & (d_fwd > D_MIN) & (d_fwd < D_MAX)
    obs = pts[keep]
    obs_fwd, obs_lat, obs_h = d_fwd[keep], d_lat[keep], h_pts[keep]

    # 栅格: 行=前向距离(行0最近), 列=方位角
    half_fov = np.arctan((W / 2) / fx)
    az = np.arctan2(obs_lat, obs_fwd)
    rows = ((obs_fwd - D_MIN) / (D_MAX - D_MIN) * N_ROWS).astype(int).clip(0, N_ROWS - 1)
    cols = ((az + half_fov) / (2 * half_fov) * N_COLS).astype(int).clip(0, N_COLS - 1)

    counts = np.zeros((N_ROWS, N_COLS), dtype=int)
    np.add.at(counts, (rows, cols), 1)

    row_z = D_MIN + (np.arange(N_ROWS) + 0.5) * (D_MAX - D_MIN) / N_ROWS
    thresh = np.maximum(OCC_K / row_z**2, OCC_MIN).astype(int)
    grid = counts >= thresh[:, None]

    print("\n[每格点数] (行0=最近0.5m, 行9=最远5m; 列0=最左)  |阈值")
    for r in range(N_ROWS - 1, -1, -1):
        print("  " + " ".join(f"{counts[r, c]:5d}" for c in range(N_COLS))
              + f"   |{thresh[r]:4d}  {row_z[r]:.2f}m")
    print("\n[激活图] (上=远, 下=近, ■=凸起)")
    for r in range(N_ROWS - 1, -1, -1):
        print("  " + " ".join("■" if grid[r, c] else "·" for c in range(N_COLS)))
    print(f"\n激活格数: {grid.sum()} / 90")

    # ── 可视化 ──
    fig, axes = plt.subplots(1, 4, figsize=(22, 6))
    axes[0].imshow(img); axes[0].set_title("RGB"); axes[0].axis("off")
    im = axes[1].imshow(depth, cmap="turbo")
    axes[1].set_title("Metric depth (m)"); axes[1].axis("off")
    plt.colorbar(im, ax=axes[1], fraction=0.03)

    ax = axes[2]
    if len(obs):
        sub = rng.choice(len(obs), min(len(obs), 30000), replace=False)
        sc = ax.scatter(obs_lat[sub], obs_fwd[sub], c=obs_h[sub],
                        s=2, cmap="viridis", vmin=H_MIN, vmax=H_MAX)
        plt.colorbar(sc, ax=ax, fraction=0.03, label="height (m)")
    ax.set_xlim(-3.5, 3.5); ax.set_ylim(0, D_MAX + 0.5)
    ax.set_xlabel("lateral (m)"); ax.set_ylabel("forward (m)")
    ax.set_title(f"Top-down (h={cam_h:.2f}m pitch={pitch:+.0f}°)")
    ax.set_aspect("equal"); ax.grid(alpha=0.3)

    ax = axes[3]
    ax.imshow(grid, cmap="Greys", origin="lower", vmin=0, vmax=1)
    ax.set_title(f"10x9 grid ({grid.sum()} on)")
    ax.set_xlabel("col (左→右)"); ax.set_ylabel("row (近→远)")
    ax.set_xticks(range(N_COLS)); ax.set_yticks(range(N_ROWS))

    out = args.img.rsplit(".", 1)[0] + "_topdown.png"
    plt.tight_layout()
    plt.savefig(out, dpi=110)
    print(f"\n[保存] {out}")


if __name__ == "__main__":
    main()