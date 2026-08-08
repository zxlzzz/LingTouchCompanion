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
from color_detector import detect_color_grid
MIN_CLUSTER_SIZE = 2   # 4-5m 处椅子仅占 1-2 格，=3 会整块删掉


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


def _run_confirmed(mask, min_run=2):
    """标记出现在长度 >= min_run 的水平或竖直连续段里的格子。

    专门用来救细长障碍物：横放的长条气球会在同一行连续好几列命中 weak，
    竖放的会在同一列连续好几行命中——单独看每一格都可能不够 strong，但
    连续排成一条线本身就是很强的"这是个真物体"的证据。噪声是空间上乱跳
    的，几乎不会连续两格以上刚好排成一条直线，所以不会被这条规则误放行。
    """
    rows, cols = mask.shape
    confirmed = np.zeros_like(mask)

    for r in range(rows):
        run_start = None
        for c in range(cols + 1):
            hit = c < cols and mask[r, c]
            if hit and run_start is None:
                run_start = c
            elif not hit and run_start is not None:
                if c - run_start >= min_run:
                    confirmed[r, run_start:c] = True
                run_start = None

    for c in range(cols):
        run_start = None
        for r in range(rows + 1):
            hit = r < rows and mask[r, c]
            if hit and run_start is None:
                run_start = r
            elif not hit and run_start is not None:
                if r - run_start >= min_run:
                    confirmed[run_start:r, c] = True
                run_start = None

    return confirmed


def compute_obstacle_scores(
    depth_map,
    cols=GRID_COLS,
    rows=GRID_ROWS,
    roi_top=ROI_TOP_RATIO,
    roi_bottom=ROI_BOTTOM_RATIO,
    cell_percentile=CELL_OBS_PERCENTILE,
):
    """深度图 → 每格 obstacle score（未阈值化）。

    抽出来单独成一个函数，一是 depth_map_to_dot_frame 内部用，二是给
    export_sample.py 这类诊断工具直接拿原始分数矩阵可视化——两边共用
    同一份算法，不会因为诊断脚本另抄一遍逻辑而跟正式管线跑偏。

    cell_percentile 开放成参数（而不是只认 config 里的常量）是为了方便
    离线扫参数——细长障碍物（比如实测用的长条气球）只占格子宽度一小部分，
    percentile 定太高会被背景像素稀释掉，定太低又会被局部反光噪声带偏，
    两者要一起测才知道怎么取舍，见 threshold_regression_test 里的实验。

    Returns:
        scores: (rows, cols) float32，每格 P{cell_percentile} 视差 - (该行基线 + margin) - 底部惩罚
        baseline: (rows,) float32，每行的 P25 视差基线
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
    OBSTACLE_MARGIN = 0.85  # 0.60 太容易被反光/褶皱这类非几何噪声越过，调大留足余量
    scores = np.zeros((rows, cols), dtype=np.float32)

    for r in range(rows):
        ground_thresh = baseline[r] + OBSTACLE_MARGIN
        for c in range(cols):
            y0, y1 = int(r * cell_h), int((r + 1) * cell_h)
            x0, x1 = int(c * cell_w), int((c + 1) * cell_w)
            cell_vals = roi[y0:y1, x0:x1].ravel()
            scores[r, c] = np.percentile(cell_vals, cell_percentile) - ground_thresh

    # Bottom penalty: linear ramp to suppress floor
    BOTTOM_PENALTY = 0.55
    for r in range(rows):
        scores[r, :] -= BOTTOM_PENALTY * (r / max(rows - 1, 1))

    return scores, baseline


def depth_map_to_dot_frame(
    depth_map,
    cols=GRID_COLS,
    rows=GRID_ROWS,
    roi_top=ROI_TOP_RATIO,
    roi_bottom=ROI_BOTTOM_RATIO,
    adaptive=True,
    frame_bgr=None,
):
    """Convert a depth map to a 90-element binary frame.

    Pipeline:
      1. Depth→disparity (higher=closer)
      2. Per-row P25 baseline, per-cell obstacle score s_ij = P85 - (baseline + margin)
      3. Dual-threshold: T_h = Q85(S), T_l = Q72(S), 且都要求 s_ij > OBS_FLOOR
         strong: s_ij >= T_h
         weak:   s_ij >= T_l AND (有 strong 邻居 OR 同排/同列连续 >=2 格都是 weak)
      4. Top-N cap at MAX_ACTIVATIONS by score
      5. Small-cluster removal 、行跨度压缩
      6. 可选：叠加 color_detector 的专项颜色识别（frame_bgr 给了才跑）——
         深度信号在远距离会弱到测不出来，颜色不会，两个通道谁测到都点亮。

    frame_bgr: 原始 BGR 画面（不是深度图）。给了就会额外跑一遍颜色识别，
      结果跟深度管线的结果 OR 在一起。不给就是纯深度管线，行为不变。

    Returns:
        frame: uint8 array of shape (FRAME_LEN,) — 0=clear, 1=activated
    """
    scores, baseline = compute_obstacle_scores(depth_map, cols, rows, roi_top, roi_bottom)
    all_scores = scores.ravel()

    # ── 3. Dual-threshold (Q85 strong / Q72 weak+neighbour) ──
    # 78/65 太宽松：即使整帧都很平（没有真障碍），百分位仍会硬选出排名靠前
    # 的一批格子当"障碍"。调高到 85/72，只有明显跳出背景的格子才会入选。
    high_thr = np.percentile(all_scores, 85)
    low_thr = np.percentile(all_scores, 72)

    # 绝对下限：分数是相对量，百分位选的是"排名"而不是"够不够格"，光有
    # 排名不代表真的抬起来了。0.0 太松——只要比行基线略高一点点就能通过；
    # 调到 0.4（约等于 OBSTACLE_MARGIN 的一半），要求真的明显超出背景噪声。
    OBS_FLOOR = 0.4
    strong = (scores >= high_thr) & (scores > OBS_FLOOR)
    neighbour_of_strong = cv2.dilate(
        strong.astype(np.uint8), np.ones((3, 3), np.uint8), iterations=1
    ).astype(bool)

    weak = (scores >= low_thr) & (scores > OBS_FLOOR)

    # 细长物体（横放/竖放的长条气球）单格往往连 weak 门槛都压不稳，但会连续
    # 好几格都在 weak 附近——这种"连续同排/同列命中"本身就是强证据，不需要
    # 旁边有 strong 格子撑腰也能确认。反光噪声那类东西是空间上乱跳的，很难
    # 连续两格以上刚好排成一条直线，所以这条规则不会把噪声也放进来。
    weak_run_confirmed = _run_confirmed(weak, min_run=2)

    grid = strong | (weak & neighbour_of_strong) | weak_run_confirmed

    # ── 4. Top-N cap by score ──
    active_pos = np.argwhere(grid)
    if len(active_pos) > MAX_ACTIVATIONS:
        active_scores = [scores[r, c] for r, c in active_pos]
        order = np.argsort(active_scores)[::-1]
        keep = active_pos[order[:MAX_ACTIVATIONS]]
        grid[:] = False
        grid[keep[:, 0], keep[:, 1]] = True

    # ── 5. 小连通区过滤 + 行跨度压缩（只针对深度通道）──
    # 注意：这里保持摄像头视角（不镜像），因为这个 frame 同时喂给屏幕预览
    # （要和原画面/热力图方向一致）。镜像是"设备触点朝向使用者"这一硬件
    # 特性，只应在真正打包发给设备前做一次，见 mirror_frame_horizontal()。
    active = grid.copy()
    active = _remove_small_clusters(active, cols, rows)
    active = _cap_cluster_row_span(active, cols, rows)

    # ── 6. 颜色专项通道叠加（可选）──
    # 故意放在"小连通区过滤"之后、"补孤点"之前 OR 进来：颜色是专门针对
    # 已知物体的强信号，哪怕远距离只点亮一个格子也是有意义的检测，不应该
    # 被"连通区太小当噪声删掉"这条规则误伤（那条规则是给深度通道的杂散
    # 噪点准备的）；但还是要过一遍行跨度压缩，避免一大片同色背景把很多
    # 格子点亮，也要一起走最后的"补孤点"，跟深度通道的孤点一视同仁。
    if frame_bgr is not None:
        color_grid = detect_color_grid(frame_bgr, cols, rows, roi_top, roi_bottom)
        if color_grid.any():
            color_grid = _cap_cluster_row_span(color_grid.copy(), cols, rows)
            active = active | color_grid

    active = _grow_isolated_dots(active, cols, rows)
    frame = active.reshape(-1).astype(np.uint8)
    return frame


def mirror_frame_horizontal(frame, cols=GRID_COLS, rows=GRID_ROWS):
    """左右镜像一个展平的 90 点帧。

    设备贴身佩戴、摄像头朝外时，触点面朝向使用者，和摄像头拍到的画面
    左右相反，需要在发给设备前镜像一次抵消。只在"打包发送给硬件"这
    一步调用——预览/调试显示应保持摄像头原始视角，不要调用这个。
    """
    g = np.asarray(frame).reshape(rows, cols)
    return g[:, ::-1].reshape(-1).astype(np.uint8).copy()


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
    frame = _filter_small_clusters(frame, GRID_COLS, GRID_ROWS)
    return frame


MAX_CLUSTER_ROW_SPAN = 2  # 行=远近编码，一个物体理论上只在一个距离出现；
                          # 跨太多行往往是双阈值/膨胀带来的富余，不是真信息


def _cap_cluster_row_span(active, cols=GRID_COLS, rows=GRID_ROWS, max_rows=MAX_CLUSTER_ROW_SPAN):
    """把每个连通区在"行"方向压到最多 max_rows 行：保留活跃格子最密集的
    那一段连续行，其余清空。长条形障碍物（横放/竖放的气球）经常因为双阈值
    的邻域确认规则蔓延到好几行，实际只需要标出"大概在哪个距离"，不需要
    整条长这么高地凸起来，减少同时抬起的点数，画面才不会看着乱。"""
    structure = np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]], dtype=np.uint8)
    labeled, n_features = ndimage.label(active, structure=structure)

    for label_id in range(1, n_features + 1):
        mask = (labeled == label_id)
        rows_touched = np.where(mask.any(axis=1))[0]
        r_min, r_max = int(rows_touched.min()), int(rows_touched.max())
        span = r_max - r_min + 1
        if span <= max_rows:
            continue

        per_row_count = mask.sum(axis=1)
        best_start, best_sum = r_min, -1
        for start in range(r_min, r_max - max_rows + 2):
            s = int(per_row_count[start:start + max_rows].sum())
            if s > best_sum:
                best_sum, best_start = s, start
        keep_rows = set(range(best_start, best_start + max_rows))

        for r in range(r_min, r_max + 1):
            if r not in keep_rows:
                active[r, :][mask[r, :]] = 0

    return active


def _remove_small_clusters(active, cols=GRID_COLS, rows=GRID_ROWS):
    """去掉小于 MIN_CLUSTER_SIZE 的连通区（4/8-连通噪点）。"""
    if active.sum() == 0:
        return active
    structure = np.array([[0, 1, 0],
                          [1, 1, 1],
                          [0, 1, 0]], dtype=np.uint8)
    labeled, n_features = ndimage.label(active, structure=structure)
    if n_features > 1:
        for label_id in range(1, n_features + 1):
            mask = (labeled == label_id)
            if mask.sum() < MIN_CLUSTER_SIZE:
                active[mask] = 0
    return active


def _grow_isolated_dots(active, cols=GRID_COLS, rows=GRID_ROWS):
    """只把"孤点"（整个连通区就 1 格）补成 2 格保证摸得到，已经有面积的
    连通区不再整体膨胀——用户反馈同时凸起太多显得乱，这一步要往保守收，
    不需要再额外放大已经能感知到的区域。"""
    if active.sum() == 0:
        return active
    structure = np.array([[0, 1, 0],
                          [1, 1, 1],
                          [0, 1, 0]], dtype=np.uint8)
    labeled, n_features = ndimage.label(active, structure=structure)
    for label_id in range(1, n_features + 1):
        mask = (labeled == label_id)
        if mask.sum() == 1:
            r, c = np.argwhere(mask)[0]
            if r + 1 < rows:
                active[r + 1, c] = 1
            elif r - 1 >= 0:
                active[r - 1, c] = 1
    return active


def _filter_small_clusters(frame, cols=GRID_COLS, rows=GRID_ROWS):
    """1. 去掉小于 MIN_CLUSTER_SIZE 的连通区（4/8-连通噪点）
       2. 把每个连通区的行跨度压到最多 MAX_CLUSTER_ROW_SPAN 行
       3. 补孤点
    """
    active = frame.reshape(rows, cols)
    if active.sum() == 0:
        return frame

    active = _remove_small_clusters(active, cols, rows)
    active = _cap_cluster_row_span(active, cols, rows)
    active = _grow_isolated_dots(active, cols, rows)

    return active.reshape(-1).astype(np.uint8)


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
