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
    DANGER_NEAR_M,
    WARNING_MEDIUM_M,
    ATTENTION_FAR_M,
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
    """Render a 9×10 dot frame as a binary grid (■ = on, · = off)."""
    lines = []
    lines.append("+" + "---" * cols + "+")
    for r in range(rows):
        line = "|"
        for c in range(cols):
            pos = r * cols + c
            line += " ■ " if frame[pos] else " · "
        line += "|"
        lines.append(line)
    lines.append("+" + "---" * cols + "+")
    return "\n".join(lines)


def braille_to_dot_string(b):
    """Convert a single SMA dot state to display string."""
    return "●" if b else "○"
