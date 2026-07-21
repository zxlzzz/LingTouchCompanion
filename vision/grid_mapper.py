"""
Grid mapper — transform depth maps into 9×10 SMA-dot patterns.

The 9×10 grid = 15 braille modules × 6 SMA dots per module.
Each cell maps to one SMA dot (on=obstacle, off=clear).

Detection logic (per cell):
  1. Ground baseline: per-row median disparity (model outputs disparity, higher=closer)
  2. Dual condition: (a) P85 of cell exceeds ground + margin AND
                     (b) >= MIN_CELL_COVERAGE fraction of cell pixels exceed ground
  3. Only top MAX_ACTIVATIONS cells by obstacle margin are activated
"""

import numpy as np
import cv2
from scipy import ndimage

from config import (
    GRID_COLS,
    GRID_ROWS,
    FRAME_LEN,
    CELL_OBS_PERCENTILE,
    MIN_CELL_COVERAGE,
    MAX_ACTIVATIONS,
    ROI_TOP_RATIO,
    ROI_BOTTOM_RATIO,
)
MIN_CLUSTER_SIZE = 3


def _build_ground_baseline(roi, rows):
    """Build per-row baseline from row-wise statistics.

    baseline[r] = P25 of row r's disparity values.
      P25 captures the background depth plane for that row
      (walls for top rows, floor for bottom rows).

    Returns baseline array of shape (rows,).
    """
    rh = roi.shape[0]
    cell_h = rh / rows

    baseline = np.zeros(rows, dtype=np.float32)
    for r in range(rows):
        y0 = int(r * cell_h)
        y1 = int((r + 1) * cell_h)
        row_data = roi[y0:y1, :].ravel()
        baseline[r] = np.percentile(row_data, 25)

    return baseline


def depth_map_to_dot_frame(
    depth_map,
    cols=GRID_COLS,
    rows=GRID_ROWS,
    roi_top=ROI_TOP_RATIO,
    roi_bottom=ROI_BOTTOM_RATIO,
    adaptive=True,
):
    """Convert a depth map to a 90-element binary frame.

    Pipeline:
      1. Depth→disparity (higher=closer)
      2. Per-row P25 baseline, per-cell obstacle score s_ij = P85 - (baseline + margin)
      3. Dual-threshold: T_h = Q78(S), T_l = Q65(S)
         strong: s_ij >= T_h
         weak:   s_ij >= T_l AND has strong neighbour (3×3)
      4. Top-N cap at MAX_ACTIVATIONS by score
      5. Small-cluster removal

    Returns:
        frame: uint8 array of shape (FRAME_LEN,) — 0=clear, 1=activated
    """
    h, w = depth_map.shape

    # ── 1. Depth → disparity + crop ROI ──
    disparity = -depth_map.astype(np.float32)
    y_start = int(h * roi_top)
    y_end = int(h * (1.0 - roi_bottom))
    roi = disparity[y_start:y_end, :]
    rh, rw = roi.shape

    cell_h = rh / rows
    cell_w = rw / cols

    # ── 2. Per-cell obstacle scores ──
    baseline = _build_ground_baseline(roi, rows)
    OBSTACLE_MARGIN = 0.60
    scores = np.zeros((rows, cols), dtype=np.float32)

    for r in range(rows):
        ground_thresh = baseline[r] + OBSTACLE_MARGIN
        for c in range(cols):
            y0, y1 = int(r * cell_h), int((r + 1) * cell_h)
            x0, x1 = int(c * cell_w), int((c + 1) * cell_w)
            cell_vals = roi[y0:y1, x0:x1].ravel()
            scores[r, c] = np.percentile(cell_vals, CELL_OBS_PERCENTILE) - ground_thresh

    # Bottom penalty: linear ramp to suppress floor
    BOTTOM_PENALTY = 0.55
    for r in range(rows):
        scores[r, :] -= BOTTOM_PENALTY * (r / max(rows - 1, 1))

    all_scores = scores.ravel()

    # ── 3. Dual-threshold (Q78 strong / Q65 weak+neighbour) ──
    high_thr = np.percentile(all_scores, 78)
    low_thr = np.percentile(all_scores, 65)

    strong = scores >= high_thr
    neighbour_of_strong = cv2.dilate(
        strong.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=1
    ).astype(bool)

    weak = scores >= low_thr
    grid = strong | (weak & neighbour_of_strong)

    # ── 4. Top-N cap by score ──
    active_pos = np.argwhere(grid)
    if len(active_pos) > MAX_ACTIVATIONS:
        active_scores = [scores[r, c] for r, c in active_pos]
        order = np.argsort(active_scores)[::-1]
        keep = active_pos[order[:MAX_ACTIVATIONS]]
        grid[:] = False
        grid[keep[:, 0], keep[:, 1]] = True

    # ── 5. Flatten + small-cluster removal ──
    frame = np.zeros(FRAME_LEN, dtype=np.uint8)
    for r in range(rows):
        for c in range(cols):
            if grid[r, c]:
                frame[r * cols + c] = 1

    frame = _filter_small_clusters(frame, cols, rows)
    return frame


# Backward-compat alias
depth_map_to_braille_frame = depth_map_to_dot_frame


# ═══════════════════════════════════════════════════════════
#  XY ground-plane projection (bird's-eye view)
# ═══════════════════════════════════════════════════════════

def depth_map_to_xy_frame(depth_map):
    """IPM: Inverse Perspective Mapping → XY ground-plane grid.

    Method 1 (user-specified):
      1. r = K⁻¹·[u,v,1]ᵀ  →  ray direction in camera space
      2. Apply camera pitch rotation R_θ
      3. Camera centre C = (0, 0, h).  Ray: P = C + λ·R_θ·r
      4. Ground plane Z=0  →  λ = -h / (R_θ·r)_z
      5. World point on ground:  X = λ·(R_θ·r)_x,  Y = λ·(R_θ·r)_y

    Obstacle detection: compare actual depth D(u,v) against expected
    ground depth at that (X,Y).  If D is significantly smaller → obstacle.

    Auto-scale: monocular depth is not metric, so depths are scaled
    per frame.  Ground/obstacle separation uses relative depth ratios.
    """
    d = depth_map.astype(np.float32)
    h_img, w_img = d.shape
    fin = np.isfinite(d) & (d > 0) & (d < 50)
    if fin.sum() < 500:
        return depth_map_to_dot_frame(depth_map)

    # ── Camera geometry (chest-mounted) ──
    cam_h = 1.30                    # metres above ground
    pitch_deg = 8.0                 # slight downward tilt (chest-mount)
    pitch_rad = np.radians(pitch_deg)

    fov_h_deg = 65.0
    cx, cy = w_img / 2.0, h_img / 2.0
    fx = cx / np.tan(np.radians(fov_h_deg / 2))
    fy = fx  # square

    # ── 1. Ray directions in camera space ──
    uu = np.arange(w_img, dtype=np.float32)
    vv = np.arange(h_img, dtype=np.float32)
    U, V = np.meshgrid(uu, vv)

    rx = (U - cx) / fx
    ry = (V - cy) / fy
    rz = np.ones_like(rx)
    r_norm = np.sqrt(rx*rx + ry*ry + rz*rz)
    rx /= r_norm; ry /= r_norm; rz /= r_norm

    # ── 2. Rotate by camera pitch (about X axis) ──
    # Level camera looks +Z; pitch down rotates +Z toward +Y.
    # R_θ = [[1, 0, 0], [0, cosθ, -sinθ], [0, sinθ, cosθ]]
    cos_t = np.cos(pitch_rad)
    sin_t = np.sin(pitch_rad)
    ry_rot = cos_t * ry - sin_t * rz
    rz_rot = sin_t * ry + cos_t * rz

    # ── 3. Intersect with ground Z=0 ──
    # Ray:  (0, 0, h) + λ·(rx, ry_rot, rz_rot)
    # Z=0:  h + λ·rz_rot = 0  →  λ = -h / rz_rot
    # Valid only where rz_rot < 0 (ray points downward toward ground)
    pointing_down = (rz_rot < -0.001)

    lam = np.zeros_like(d)
    lam[pointing_down] = -cam_h / rz_rot[pointing_down]

    # ── 4. World coords on ground ──
    X_world = rx * lam        # lateral, right = +
    Y_world = ry_rot * lam    # forward (in rotated space Y is forward)

    # ── 5. Expected depth at world point ──
    # From camera to (X, Y, 0): distance = sqrt(X² + Y² + h²)
    expected_depth = np.sqrt(X_world**2 + Y_world**2 + cam_h**2)
    expected_depth[~pointing_down] = np.inf

    # ── 6. Auto-scale: monocular depth has no metric scale ──
    # Align expected_depth median to actual depth median over ground region.
    ground_region = pointing_down & fin & (Y_world > 0.3) & (Y_world < 10)
    if ground_region.sum() < 200:
        return depth_map_to_dot_frame(depth_map)

    exp_vals = expected_depth[ground_region]
    act_vals = d[ground_region]
    scale = np.median(act_vals) / max(np.median(exp_vals), 1e-6)
    expected_depth_scaled = expected_depth * scale

    # ── 7. Obstacle = actual depth ≪ expected ground depth ──
    # If a pixel is an obstacle (above ground), its 3D point is at (X,Y,Z>0)
    # but IPM maps it to (X', Y', 0) at a farther distance.
    # So: obstacle → D_actual < D_expected * ratio
    depth_ratio = np.full_like(d, 1.0, dtype=np.float32)
    depth_ratio[ground_region] = d[ground_region] / np.maximum(
        expected_depth_scaled[ground_region], 0.1
    )

    OBS_RATIO = 0.70
    is_obstacle = fin & pointing_down & (depth_ratio < OBS_RATIO)
    is_obstacle &= (Y_world > 0.3) & (Y_world < 20)

    if is_obstacle.sum() < 50:
        return depth_map_to_dot_frame(depth_map)

    # ── 8. Grid geometry — auto-scale Y to fit ──
    Y_obs = Y_world[is_obstacle]
    X_obs = X_world[is_obstacle]

    y_lo, y_hi = np.percentile(Y_obs, 2), np.percentile(Y_obs, 98)
    y_range = max(y_hi - y_lo, 0.5)
    x_half = max(np.percentile(np.abs(X_obs), 98), 0.5)

    cell_m = 0.50
    GRID_Y_NEAR = 0.3
    GRID_Y_FAR = GRID_Y_NEAR + GRID_ROWS * cell_m
    GRID_X_HALF = GRID_COLS * cell_m / 2

    Y_scaled = GRID_Y_NEAR + (GRID_Y_FAR - GRID_Y_NEAR) * (Y_obs - y_lo) / y_range
    X_scaled = X_obs * (GRID_X_HALF / x_half)

    in_bounds = (
        (Y_scaled >= GRID_Y_NEAR) & (Y_scaled <= GRID_Y_FAR) &
        (np.abs(X_scaled) <= GRID_X_HALF)
    )
    if not in_bounds.any():
        return depth_map_to_dot_frame(depth_map)

    Y_in, X_in = Y_scaled[in_bounds], X_scaled[in_bounds]

    # ── 9. Bin with confidence weight ──
    ci = np.clip(((X_in + GRID_X_HALF) / cell_m).astype(np.int32), 0, GRID_COLS - 1)
    ri_row = np.clip(((Y_in - GRID_Y_NEAR) / cell_m).astype(np.int32), 0, GRID_ROWS - 1)
    ri = GRID_ROWS - 1 - ri_row

    # Weight: how strongly this pixel departs from ground expectation
    w = 1.0 - depth_ratio[is_obstacle][in_bounds]
    w = np.clip(w, 0, 1)

    cell_score = np.zeros((GRID_ROWS, GRID_COLS), dtype=np.float32)
    np.add.at(cell_score, (ri, ci), w)

    if cell_score.max() <= 0:
        return depth_map_to_dot_frame(depth_map)

    # ── 10. Threshold + cap ──
    all_s = cell_score.ravel()
    hi = np.percentile(all_s[all_s > 0], 75)
    lo = np.percentile(all_s[all_s > 0], 60)
    strong = cell_score >= hi
    neighbour = cv2.dilate(strong.astype(np.uint8),
                           np.ones((3, 3), np.uint8), iterations=1).astype(bool)
    grid = strong | ((cell_score >= lo) & neighbour)

    ap = np.argwhere(grid)
    if len(ap) > MAX_ACTIVATIONS:
        sv = [cell_score[r, c] for r, c in ap]
        grid[:] = False
        grid[tuple(ap[np.argsort(sv)[::-1][:MAX_ACTIVATIONS]].T)] = True

    frame = np.zeros(FRAME_LEN, dtype=np.uint8)
    for r in range(GRID_ROWS):
        for c in range(GRID_COLS):
            if grid[r, c]:
                frame[r * GRID_COLS + c] = 1
    return frame


def _filter_small_clusters(frame, cols=GRID_COLS, rows=GRID_ROWS):
    """Remove clusters smaller than MIN_CLUSTER_SIZE. 4-connected."""
    active = frame.reshape(rows, cols)
    if active.sum() == 0:
        return frame

    structure = np.array([[0, 1, 0],
                          [1, 1, 1],
                          [0, 1, 0]], dtype=np.uint8)
    labeled, n_features = ndimage.label(active, structure=structure)

    if n_features <= 1:
        return frame

    for label_id in range(1, n_features + 1):
        mask = (labeled == label_id)
        if mask.sum() < MIN_CLUSTER_SIZE:
            for r in range(rows):
                for c in range(cols):
                    if mask[r, c]:
                        frame[r * cols + c] = 0
    return frame


# ═══════════════════════════════════════════════════════════
#  Edge activation → SMA dot encoding
# ═══════════════════════════════════════════════════════════

def edge_cells_to_braille_frame(activated_cells, cols=GRID_COLS, rows=GRID_ROWS):
    """Convert activated grid cells (from edge detection) to a 90-dot frame."""
    frame = np.zeros(FRAME_LEN, dtype=np.uint8)
    for r, c in activated_cells:
        pos = r * cols + c
        if 0 <= pos < FRAME_LEN:
            frame[pos] = 1
    return frame


# ═══════════════════════════════════════════════════════════
#  Mode-specific processing
# ═══════════════════════════════════════════════════════════

def apply_rapid_avoid_mode(frame):
    """RAPID_AVOID: emphasize near-field (bottom ~40% rows)."""
    for pos in range(FRAME_LEN):
        row = pos // GRID_COLS
        if row < int(GRID_ROWS * 0.6):
            frame[pos] = 0
    return frame


def apply_local_zoom_mode(frame, depth_map=None, zoom_range_m=1.5):
    """LOCAL_ZOOM: only show obstacles within zoom_range_m."""
    if depth_map is not None:
        h, w = depth_map.shape
        y_start = int(h * ROI_TOP_RATIO)
        y_end = int(h * (1.0 - ROI_BOTTOM_RATIO))
        roi = depth_map[y_start:y_end, :]
        rh, rw = roi.shape
        cell_h, cell_w = rh / GRID_ROWS, rw / GRID_COLS
        for r in range(GRID_ROWS):
            for c in range(GRID_COLS):
                pos = r * GRID_COLS + c
                y0, y1 = int(r * cell_h), int((r + 1) * cell_h)
                x0, x1 = int(c * cell_w), int((c + 1) * cell_w)
                if np.min(roi[y0:y1, x0:x1]) > zoom_range_m:
                    frame[pos] = 0
    return frame


# ═══════════════════════════════════════════════════════════
#  Visualization
# ═══════════════════════════════════════════════════════════

def visualize_frame(frame, cols=GRID_COLS, rows=GRID_ROWS):
    """Render a 9×10 dot frame as a binary grid."""
    lines = []
    lines.append("+" + "---" * cols + "+")
    for r in range(rows):
        line = "|"
        for c in range(cols):
            pos = r * cols + c
            line += " # " if frame[pos] else " . "
        line += "|"
        lines.append(line)
    lines.append("+" + "---" * cols + "+")
    return "\n".join(lines)


def braille_to_dot_string(b):
    """Convert a single SMA dot state to display string."""
    return "#" if b else "."
