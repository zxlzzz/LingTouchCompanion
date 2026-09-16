#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
灵触随行 — 离线验证管线（metric 深度 → 点云 → 地面拟合 → 高度过滤 → 俯视 10x9 栅格）

输入:
  --img    原始照片 (jpg/png)
  --depth  官方 run.py --save-numpy 输出的 .npy (米制深度, HxW float)
  --fx     焦距(像素)。二选一:
  --calib  "PX REAL DIST"  标定物像素宽 实际宽(m) 拍摄距离(m) → fx = PX*DIST/REAL
  --profile JSON   显式加载参数配置；不指定时复现旧映射
  --outdir DIR     图片、栅格和诊断 JSON 的输出目录

用法:
  python topdown_pipeline.py --img 1.jpg --depth 1.npy --calib "1200 0.90 3.0"
  python topdown_pipeline.py --img 1.jpg --depth 1.npy --fx 2300

输出:
  <img名>_topdown.png   四联图: 原图 / 深度 / 俯视点云 / 10x9栅格
  <img名>_grid.npy / _grid.json  栅格、每格点数、阈值和地面诊断
  CLI 和在线服务都调用 depth_to_grid，使用相同的两遍尺度锚定流程。

地面拟合(ransac_ground): RANSAC 粗定位平面 → 最小二乘精修 → REFIT_ROUNDS(默认3)轮
非对称迭代剔除(地面以下容忍15cm, 以上只容忍5cm, 专挑椅子腿这类贴地but更高的点甩掉)。
GROUND_IMG_FRAC 从 0.45 收紧到 0.25——45%时近距离物体(椅子)会占满候选带底部, 容易被
误拟合进地面里, 见仓库根目录 TOPDOWN_VALIDATION.md 的详细记录。

多障碍预览配置加入随距离变化的地面残差校正，保留不同距离的占据点，并关闭固定横向膨胀。
运行环境使用 D:/anaconda/envs/LING/python.exe；旧 lingtouch 环境的 BLAS/LAPACK 已损坏。
"""

import argparse
import json
from dataclasses import asdict, dataclass
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from PIL import Image

# ── 可调参数 ─────────────────────────────────────
STRIDE        = 8          # 像素下采样步长(3072x4096 → ~19万点)
H_MIN, H_MAX  = 0.10, 1.80 # 离地高度保留区间(m): 剔地板/天花板
D_MIN, D_MAX  = 1.0, 5.0   # 前向距离区间(m) → 10行
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
# 占据判定: 阈值 = 该格"完全被障碍物填满时应有的点数" × OCC_FILL_FRAC。
# 为什么不用绝对点数(旧的 OCC_K/z²): 绝对阈值同时耦合了图像分辨率和 stride——
# 手机实际拍到 1080 宽而不是标定的 3072 宽时, 每格点数掉到 12%, 绝对阈值不变
# 就会让整个栅格全空, 而且"全空"在这套系统里恰好等于"前方通畅", 是最危险的
# 静默失败方向。按比例算的话 expected ∝ W × fy ∝ W², 分辨率变化自动抵消。
OCC_FILL_FRAC = 0.035  # 该格预期可见面积被占到这个比例才算有障碍(0.05→0.035, 2026-08-09
                        # 用 chair_3m 实测数据调的: 椅子2.8m那格497点在0.05下阈值527没过线,
                        # 调到0.035阈值降到~369, 497/416两格都过线且有13-30%余量; 同一张图里
                        # 噪声格最高才96-192, 离369还远, 不会跟着被误触发)
OCC_MIN       = 8      # 绝对下限, 防止极远处 expected 太小导致噪点过关
CAM_H_TRUE = 1.40          # 胸挂实测相机高度(m) —— 尺度锚定基准, 见 TOPDOWN_VALIDATION.md
# ────────────────────────────────────────────────


@dataclass(frozen=True)
class TopdownConfig:
    """Explicit per-run parameters; omitting a profile preserves the legacy mapping.

    focal_scale multiplies the supplied, resolution-scaled fx/fy. A fitted value
    is an effective alignment parameter, not an independently measured intrinsic.
    """
    cam_h_true: float = CAM_H_TRUE
    focal_scale: float = 1.0
    stride: int = STRIDE
    h_min: float = H_MIN
    h_max: float = H_MAX
    d_min: float = D_MIN
    d_max: float = D_MAX
    ground_img_frac: float = GROUND_IMG_FRAC
    ground_d_max: float = GROUND_D_MAX
    ransac_iters: int = RANSAC_ITERS
    ransac_tol: float = RANSAC_TOL
    refit_low: float = REFIT_LOW
    refit_high: float = REFIT_HIGH
    refit_rounds: int = REFIT_ROUNDS
    occ_fill_frac: float = OCC_FILL_FRAC
    occ_min: int = OCC_MIN
    max_cells_per_col: int = 2
    dilation_cols: int = 1
    floor_correction: bool = False
    floor_bin_m: float = 0.4
    floor_quantile: float = 0.3

    def __post_init__(self):
        if not all(np.isfinite(v) for v in asdict(self).values()):
            raise ValueError("All top-down parameters must be finite")
        if not (0 < self.h_min < self.h_max and 0 < self.d_min < self.d_max):
            raise ValueError("Invalid height/distance interval")
        if min(self.cam_h_true, self.focal_scale, self.stride, self.ground_d_max,
               self.ransac_iters, self.ransac_tol, self.occ_fill_frac, self.occ_min) <= 0:
            raise ValueError("Scale, sampling and threshold parameters must be positive")
        if not (0 < self.ground_img_frac <= 1 and self.refit_low < self.refit_high):
            raise ValueError("Invalid ground-fit parameters")
        if not (1 <= self.max_cells_per_col <= N_ROWS and 0 <= self.dilation_cols < N_COLS):
            raise ValueError("Invalid occupancy support limits")
        for name in ('stride', 'ransac_iters', 'refit_rounds', 'occ_min',
                     'max_cells_per_col', 'dilation_cols'):
            if not isinstance(getattr(self, name), int) or getattr(self, name) < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        if self.floor_bin_m <= 0 or not 0 < self.floor_quantile < 1:
            raise ValueError("Invalid floor correction settings")
        if not isinstance(self.floor_correction, bool):
            raise ValueError("floor_correction must be boolean")

    @classmethod
    def load(cls, path):
        return cls(**json.loads(Path(path).read_text(encoding='utf-8')))


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


def ransac_ground(pts, vs, img_h, rng, config=None):
    """底部画面点 RANSAC 拟合地面平面。返回 (unit normal 指向相机侧, d) 使 n·p + d = 0"""
    cfg = config or TopdownConfig()
    cand = pts[(vs > img_h * (1 - cfg.ground_img_frac)) & (pts[:, 2] < cfg.ground_d_max)]
    if len(cand) < 100:
        raise RuntimeError("地面候选点不足——画面底部没拍到地板?")
    best_n, best_d, best_cnt = None, None, -1
    for _ in range(cfg.ransac_iters):
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
        cnt = np.sum(np.abs(matvec(cand, n) + d) < cfg.ransac_tol)
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
    inl = cand[np.abs(matvec(cand, best_n) + best_d) < cfg.ransac_tol]
    if len(inl) < 3:
        raise RuntimeError("地面共识点不足")
    n, d = _refit(inl)

    # 后续 REFIT_ROUNDS 轮: 用当前平面重新量全部候选点的带符号残差,
    # 非对称剔除(地面以下容忍15cm, 以上只容忍5cm——专挑椅子腿这类"更高"的点甩), 再精修。
    for _ in range(cfg.refit_rounds):
        resid = matvec(cand, n) + d
        inl_next = cand[(resid > cfg.refit_low) & (resid < cfg.refit_high)]
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


def correct_floor_height(heights, forward, image_rows, image_height, config):
    """Remove a smooth range-dependent floor residual in monocular depth.

    This compensates a curved estimated floor after planar pose/scale recovery;
    it does not change forward distances or infer hidden obstacles. Quantiles
    use depth points only, with no RGB masks or scene-specific annotations.
    The method assumes enough exposed, approximately level floor in each band.
    Missing endpoint bands are held constant, never extrapolated as a slope.
    """
    step = config.floor_bin_m
    centers = np.arange(max(.2, config.d_min - .4), config.d_max + 1.0, step)
    distances, levels = [], []
    min_points = max(20, round(len(heights) * .002))
    plausible = ((heights > -.6) & (heights < .15)
                 & (image_rows > image_height * .15))
    for center in centers:
        band = plausible & (np.abs(forward - center) < step * .75)
        if np.count_nonzero(band) < min_points:
            continue
        distances.append(float(center))
        levels.append(float(np.quantile(heights[band], config.floor_quantile)))
    if len(distances) < 4 or distances[-1] - distances[0] < 1.2:
        raise RuntimeError("地面残差校正缺少足够的可见地面支撑")
    trend = np.interp(forward, distances, levels)
    return heights - trend, dict(distance_m=distances, residual_m=levels,
                                 min_points_per_band=min_points)


def occupancy(counts, W, fy, stride, config=None):
    """点数 -> 占据。内部 row0=近；阈值按预期可见面积缩放。

    默认每列保留最近2格并左右扩1列，兼容旧单目标设置。
    多障碍配置可保留全部10行并关闭膨胀，避免抹掉远处障碍及相邻通道。
    """
    cfg = config or TopdownConfig()
    row_z = cfg.d_min + (np.arange(N_ROWS) + 0.5) * (cfg.d_max - cfg.d_min) / N_ROWS
    # 该格填满时的像素面积: 宽 ≈ W/N_COLS(每列占的画面宽度),
    # 高 ≈ 高度保留区间在该距离上张开的像素数 (H_MAX-H_MIN)*fy/z
    expected = (W / N_COLS) * ((cfg.h_max - cfg.h_min) * fy / row_z) / (stride ** 2)
    thresh = np.maximum(expected * cfg.occ_fill_frac, cfg.occ_min).astype(int)
    passed = counts >= thresh[:, None]
    grid = np.zeros_like(passed)
    for c in range(N_COLS):
        rr = np.nonzero(passed[:, c])[0]
        for r in rr[:cfg.max_cells_per_col]:
            grid[r, c] = True       # 此处 row0=最近

    # 每个命中格同行左右各扩1列(3格宽, 越界截断)。椅子这类紧凑物体过线后往往只有
    # 1-2个孤立点, 触感上跟"一根针"没区别, 找不到; 膨胀成一小块(3-6点)更好摸。
    # 宽障碍物(墙/大平面)本来就跨多列, 膨胀只是边缘各宽一格, 不影响形状特征。
    # 代价是方位分辨率变粗(±5.6°), 对"找到一把椅子"这个任务无所谓。
    g2 = grid.copy()
    for delta in range(1, cfg.dilation_cols + 1):
        g2[:, :-delta] |= grid[:, delta:]
        g2[:, delta:] |= grid[:, :-delta]
    grid = g2

    return grid, thresh


def depth_to_grid(depth, fx, fy=None, cam_h_true=None, stride=None,
                  config=None, return_details=False):
    """metric 深度图 -> 10x9 俯视占据栅格(bool)。供 visionss/phone_server.py 按键回调直接调用。

    与 validate_distance.py 的 analyze() 同一套两遍流程:
      1. 原始深度先拟合一次地面, 拿 cam_h_raw 算 scale = cam_h_true / cam_h_raw
      2. 深度整体乘 scale 后重新 backproject + 拟合地面(此时 cam_h 应回到 cam_h_true 附近)
      3. 高度过滤 + 前向/方位分箱 + occupancy() 占据判定(与 main() 的 CLI 路径共用)

    config 接受 TopdownConfig；显式 cam_h_true/stride 覆盖配置里的对应值。
    return_details=True 返回包含 grid、点云和地面诊断的字典，仍使用同一计算路径。

    返回: (10,9) bool ndarray。**row 0 = 最远(默认5.0m), row 9 = 最近(默认1.0m)**
          —— 和 vision/frame_converter.py 的约定一致(row0=远), 这样 grid_to_bytes
          可以原样复用那份已经在硬件上验证过的映射, 近场落在 M13-M15(坏点最少的
          一行, 这是 PCB 180°反装的全部目的)。俯视栅格内部是按"row0=最近"算的,
          在函数出口统一翻一次行, 不要在别处再翻第二次。
          col 0..8 = 方位角, 左到右(画面左→右, 未做设备穿戴镜像 —— 镜像交给
          frame_converter.mirror_grid_horizontal, 只在打包发给硬件前调用一次)。

    深度不合法(地面候选点不足/找不到地面)时返回 **None**, 不是全 False 栅格。
    全 False 在这套设备上恰好等于"前方通畅", 是最危险的误导方向; 调用方拿到 None
    应该选择不下发并提示重扫, 而不是把一帧废深度图当成空场送到使用者手上。
    """
    cfg = config or TopdownConfig()
    cam_h_true = cfg.cam_h_true if cam_h_true is None else cam_h_true
    stride = cfg.stride if stride is None else stride
    if not np.isfinite(fx) or fx <= 0 or (fy is not None and (not np.isfinite(fy) or fy <= 0)):
        raise ValueError("fx/fy must be positive finite focal lengths")
    if not np.isfinite(cam_h_true) or cam_h_true <= 0 or not isinstance(stride, int) or stride <= 0:
        raise ValueError("Invalid camera height or stride")
    depth = np.asarray(depth, dtype=np.float32)
    if depth.ndim != 2:
        raise ValueError("Depth must be a 2D array")
    H, W = depth.shape
    cx, cy = W / 2, H / 2
    fy = (fx if fy is None else fy) * cfg.focal_scale
    fx = fx * cfg.focal_scale
    rng = np.random.default_rng(0)

    try:
        pts, vs = backproject(depth, fx, fy, cx, cy, stride)
        _, _, cam_h_raw, _, _ = ransac_ground(pts, vs, H, rng, cfg)
        if not np.isfinite(cam_h_raw) or cam_h_raw < 1e-6:
            raise RuntimeError("无效的地面尺度")
        scale = cam_h_true / cam_h_raw
        pts, vs = backproject(depth * scale, fx, fy, cx, cy, stride)
        n, d, cam_h_fit, pitch, inlier_frac = ransac_ground(pts, vs, H, rng, cfg)
    except RuntimeError as e:
        print(f"[topdown] 地面拟合失败, 本帧作废(不下发): {e}")
        return None

    h_pts = matvec(pts, n) + d
    fwd, right = ground_frame(n, pts)
    d_fwd = matvec(pts, fwd)
    d_lat = matvec(pts, right)
    raw_heights = h_pts.copy()
    floor_curve = None
    if cfg.floor_correction:
        try:
            h_pts, floor_curve = correct_floor_height(h_pts, d_fwd, vs, H, cfg)
        except RuntimeError as e:
            print(f"[topdown] {e}; 本帧作废(不下发)")
            return None

    keep = (h_pts > cfg.h_min) & (h_pts < cfg.h_max) & (d_fwd > cfg.d_min) & (d_fwd < cfg.d_max)
    obs_fwd, obs_lat = d_fwd[keep], d_lat[keep]

    half_fov = np.arctan((W / 2) / fx)
    az = np.arctan2(obs_lat, obs_fwd)
    rows = ((obs_fwd - cfg.d_min) / (cfg.d_max - cfg.d_min) * N_ROWS).astype(int).clip(0, N_ROWS - 1)
    cols = ((az + half_fov) / (2 * half_fov) * N_COLS).astype(int).clip(0, N_COLS - 1)

    counts = np.zeros((N_ROWS, N_COLS), dtype=int)
    np.add.at(counts, (rows, cols), 1)

    grid, thresholds = occupancy(counts, W, fy, stride, cfg)
    if return_details:
        return dict(grid=grid[::-1].copy(), counts=counts[::-1].copy(),
                    thresholds=thresholds[::-1].copy(), cam_h_raw=float(cam_h_raw),
                    scale=float(scale), cam_h_fit=float(cam_h_fit), pitch_deg=float(pitch),
                    ground_inliers=float(inlier_frac), fx=float(fx), fy=float(fy),
                    obs_forward=obs_fwd, obs_lateral=obs_lat, obs_height=h_pts[keep],
                    floor_curve=floor_curve, sample_image_rows=vs, sample_keep=keep,
                    sample_image_cols=np.rint(pts[:, 0] * fx / pts[:, 2] + cx).astype(int),
                    sample_height=h_pts, sample_raw_height=raw_heights,
                    sample_forward=d_fwd, sample_lateral=d_lat)
    return grid[::-1].copy()   # 内部 row0=最近 -> 出口 row0=最远(见 docstring)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--img", required=True)
    ap.add_argument("--depth", required=True)
    ap.add_argument("--fx", type=float)
    ap.add_argument("--calib", type=str, help='"PX REAL DIST"')
    ap.add_argument("--profile", type=Path, help="JSON parameters; omit for legacy defaults")
    ap.add_argument("--outdir", type=Path)
    args = ap.parse_args()
    cfg = TopdownConfig.load(args.profile) if args.profile else TopdownConfig()
    img = np.array(Image.open(args.img).convert("RGB"))
    depth = np.load(args.depth, allow_pickle=False).astype(np.float32)
    if depth.shape != img.shape[:2]:
        depth = np.array(Image.fromarray(depth).resize(
            (img.shape[1], img.shape[0]), Image.Resampling.BILINEAR))
    if args.calib:
        px, real, dist = map(float, args.calib.split())
        fx = px * dist / real
    else:
        fx = args.fx or img.shape[1] / (2 * np.tan(np.radians(HFOV_FALLBACK / 2)))
    result = depth_to_grid(depth, fx, config=cfg, return_details=True)
    if result is None:
        raise SystemExit("Invalid depth: no grid exported")
    grid = result['grid']
    print(f"raw height={result['cam_h_raw']:.3f}m; scale={result['scale']:.4f}; "
          f"pitch={result['pitch_deg']:.2f}deg; occupied={grid.sum()}/90")
    print("grid (top=far; left=image left):")
    for row in grid:
        print(''.join('#' if x else '.' for x in row))
    outdir = args.outdir or Path(args.img).parent
    outdir.mkdir(parents=True, exist_ok=True)
    stem = Path(args.img).stem
    np.save(outdir / f"{stem}_grid.npy", grid)
    serial = {k: v.tolist() if isinstance(v, np.ndarray) else v
              for k, v in result.items() if not k.startswith(('obs_', 'sample_'))}
    serial['parameters'] = asdict(cfg)
    (outdir / f"{stem}_grid.json").write_text(json.dumps(serial, indent=2), encoding='utf-8')
    fig, axes = plt.subplots(1, 4, figsize=(19, 6))
    axes[0].imshow(img); axes[0].set_title("RGB"); axes[0].axis("off")
    im = axes[1].imshow(depth, cmap="turbo")
    axes[1].set_title("Raw metric depth (m)"); axes[1].axis("off")
    fig.colorbar(im, ax=axes[1], fraction=.03)
    ax = axes[2]
    if len(result['obs_forward']):
        sub = np.random.default_rng(0).choice(len(result['obs_forward']),
                                              min(len(result['obs_forward']), 30000), replace=False)
        sc = ax.scatter(result['obs_lateral'][sub], result['obs_forward'][sub],
                        c=result['obs_height'][sub], s=2, cmap="viridis",
                        vmin=cfg.h_min, vmax=cfg.h_max)
        fig.colorbar(sc, ax=ax, fraction=.03, label="height (m)")
    ax.set(xlim=(-3.5, 3.5), ylim=(0, cfg.d_max + .5), xlabel="lateral (m)",
           ylabel="forward (m)", title="Ground projection")
    ax.set_aspect("equal"); ax.grid(alpha=.3)
    axes[3].imshow(grid, cmap="Greys", vmin=0, vmax=1)
    axes[3].set(title=f"10 x 9 grid ({grid.sum()} on)", xlabel="left to right", ylabel="far to near")
    fig.tight_layout()
    out = outdir / f"{stem}_topdown.png"
    fig.savefig(out, dpi=130)
    plt.close(fig)
    print(f"Saved: {out}")


if __name__ == "__main__":
    main()
