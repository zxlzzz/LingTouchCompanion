"""Single-frame measured-depth baseline. Coordinates: x right, y forward, z up."""
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class Intrinsics:
    width: int
    height: int
    fx: float
    fy: float
    cx: float
    cy: float

    def __post_init__(self):
        if min(self.width, self.height, self.fx, self.fy) <= 0:
            raise ValueError("Invalid camera intrinsics")
        if not np.isfinite([self.fx, self.fy, self.cx, self.cy]).all():
            raise ValueError("Non-finite camera intrinsics")


@dataclass(frozen=True)
class Config:
    stride: int = 3
    min_depth: float = 0.1
    max_depth: float = 5.0
    plane_tolerance: float = 0.03
    ground_tolerance: float = 0.05
    min_height: float = 0.10
    max_height: float = 1.90
    obstacle_min_points: int = 5
    ransac_iterations: int = 180


def unproject(depth_m, k):
    if depth_m.shape != (k.height, k.width):
        raise ValueError("Depth shape and intrinsics differ; resizing is not calibration")
    v, u = np.indices(depth_m.shape, dtype=np.float32)
    return np.stack(((u - k.cx) * depth_m / k.fx,
                     (v - k.cy) * depth_m / k.fy, depth_m), axis=-1)


def estimate_ground(points, config):
    """RANSAC + least squares, with height, normal and below-plane gates."""
    if len(points) < 120:
        return None, "地面候选不足"
    rng = np.random.default_rng(42)
    best = None
    best_count = 0
    for _ in range(config.ransac_iterations):
        a, b, c = points[rng.choice(len(points), 3, replace=False)]
        normal = np.cross(b - a, c - a)
        norm = np.linalg.norm(normal)
        if norm < 1e-7:
            continue
        normal = normal / norm
        offset = -np.dot(normal, a)
        if offset < 0:
            normal, offset = -normal, -offset
        if not (0.30 <= offset <= 2.3 and -normal[1] >= np.cos(np.deg2rad(65))):
            continue
        inliers = np.abs(points @ normal + offset) <= config.plane_tolerance
        count = int(inliers.sum())
        if count > best_count:
            best, best_count = inliers, count
    if best is None or best_count < 120:
        return None, "未找到可信地面"
    selected = points[best]
    center = selected.mean(axis=0)
    _, _, vh = np.linalg.svd(selected - center, full_matrices=False)
    normal = vh[-1]
    offset = -np.dot(normal, center)
    if offset < 0:
        normal, offset = -normal, -offset
    residual = points @ normal + offset
    if not (0.30 <= offset <= 2.3 and -normal[1] >= np.cos(np.deg2rad(65))):
        return None, "地面方向或相机高度异常"
    if np.mean(residual < -0.10) > 0.05:
        return None, "平面下方点过多，可能拟合到桌面"
    inliers = np.abs(residual) <= config.plane_tolerance
    if int(inliers.sum()) < 120:
        return None, "地面支持不足"
    forward = np.array([0., 0., 1.]) - normal[2] * normal
    forward /= np.linalg.norm(forward)
    if np.ptp(points[inliers] @ forward) < 0.4:
        return None, "地面覆盖不足"
    right = np.cross(forward, normal)
    return {"normal": normal, "height_m": float(offset), "forward": forward,
            "right": right, "inliers": int(inliers.sum()),
            "rms_m": float(np.sqrt(np.mean(residual[inliers] ** 2)))}, "有效"


def to_ground(points, ground):
    return np.stack((points @ ground["right"], points @ ground["forward"],
                     points @ ground["normal"] + ground["height_m"]), axis=-1)


def build_grid(points, config):
    grid = np.full((6, 9), 2, dtype=np.uint8)
    band_hits = np.zeros((6, 9), dtype=np.int32)
    floor_hits = np.zeros((24, 36), dtype=bool)
    sx = np.floor((points[:, 0] + 1.8) / 0.1).astype(np.int32)
    sy = np.floor((points[:, 1] - 1.0) / 0.1).astype(np.int32)
    inside = (sx >= 0) & (sx < 36) & (sy >= 0) & (sy < 24)
    sx, sy, heights = sx[inside], sy[inside], points[inside, 2]
    band = (heights >= config.min_height) & (heights <= config.max_height)
    np.add.at(band_hits, (5 - sy[band] // 4, sx[band] // 4), 1)
    floor = np.abs(heights) <= config.ground_tolerance
    floor_hits[sy[floor], sx[floor]] = True
    coverage = floor_hits.reshape(6, 4, 9, 4).sum(axis=(1, 3))[::-1]
    grid[(band_hits == 0) & (coverage == 16)] = 0
    grid[band_hits >= config.obstacle_min_points] = 1
    return grid, band_hits, coverage


def process_depth(depth_m, k, config=Config()):
    valid = np.isfinite(depth_m) & (depth_m >= config.min_depth) & (depth_m <= config.max_depth)
    # Invalid values must not enter matrix multiplication or integer casts.
    xyz = unproject(np.where(valid, depth_m, 0).astype(np.float32), k)
    sampled = xyz[::config.stride, ::config.stride]
    sample_valid = valid[::config.stride, ::config.stride]
    rows = np.arange(0, k.height, config.stride)[:, None]
    candidates = sampled[sample_valid & (rows >= k.height * 0.55)]
    ground, status = estimate_ground(candidates, config)
    output = {"status": status, "ground": ground, "valid": valid, "xyz": xyz,
              "valid_fraction": float(valid.mean()), "grid": np.full((6, 9), 2, dtype=np.uint8),
              "points": np.empty((0, 3)), "obstacle_points": np.empty((0, 3))}
    if ground is None:
        return output
    observed = sampled[sample_valid]
    all_heights = observed @ ground["normal"] + ground["height_m"]
    if np.mean(all_heights < -0.10) > 0.05:
        output.update(ground=None, status="全帧平面检查失败")
        return output
    points = to_ground(observed, ground)
    grid, hits, coverage = build_grid(points, config)
    band = (points[:, 2] >= config.min_height) & (points[:, 2] <= config.max_height)
    output.update(grid=grid, points=points, obstacle_points=points[band],
                  band_hits=hits, floor_subblocks=coverage)
    return output
