"""
Grid mapper — transform depth maps / edge maps into 3×5 braille patterns.

The 3×5 grid aligns with the ESP32 firmware's physical layout:
  Position  1  2  3    (top row, farthest)
  Position  4  5  6
  Position  7  8  9
  Position 10 11 12
  Position 13 14 15    (bottom row, nearest)

For depth-based mapping:
  - Each grid cell measures the minimum depth (nearest obstacle point)
  - Rows: top=farther away → bottom=closer
  - Columns: left / center / right field of view

For edge-based mapping (paper method):
  - Each grid cell is on/off (contour passes through it)
  - On cells get a fixed pattern depending on row position
"""

import numpy as np

from config import (
    GRID_COLS,
    GRID_ROWS,
    FRAME_LEN,
    DANGER_NEAR_M,
    WARNING_MEDIUM_M,
    ATTENTION_FAR_M,
    BRAILLE_ALL_ON,
    BRAILLE_NEAR,
    BRAILLE_MEDIUM,
    BRAILLE_FAR,
    BRAILLE_NONE,
    ROI_TOP_RATIO,
    ROI_BOTTOM_RATIO,
)


# ═══════════════════════════════════════════════════════════
#  Depth → Braille encoding
# ═══════════════════════════════════════════════════════════

def depth_map_to_braille_frame(
    depth_map,
    cols=GRID_COLS,
    rows=GRID_ROWS,
    roi_top=ROI_TOP_RATIO,
    roi_bottom=ROI_BOTTOM_RATIO,
    danger_near=DANGER_NEAR_M,
    warning_med=WARNING_MEDIUM_M,
    attention_far=ATTENTION_FAR_M,
):
    """Convert a depth map to a 15-byte braille frame.

    Each cell gets min-depth → dot pattern:
      < danger_near    : all 6 dots (0x3F) → urgent obstacle
      < warning_med    : 4 dots (0x2F)     → caution
      < attention_far  : 2 dots (0x09)     → light awareness
      >= attention_far : 0 dots (0x00)     → clear path

    Args:
        depth_map: (H, W) float32 array, values in meters
        cols, rows: grid dimensions (3 × 5)

    Returns:
        frame: uint8 numpy array of shape (FRAME_LEN,) — 15 bytes
    """
    h, w = depth_map.shape

    # Crop ROI
    y_start = int(h * roi_top)
    y_end = int(h * (1.0 - roi_bottom))
    roi = depth_map[y_start:y_end, :]
    rh, rw = roi.shape

    cell_h = rh / rows
    cell_w = rw / cols

    frame = np.zeros(FRAME_LEN, dtype=np.uint8)

    for r in range(rows):
        for c in range(cols):
            # Map grid position (row, col) → firmware position index (1-based → 0-based)
            pos = r * cols + c  # 0-14, matches firmware layout

            # Extract cell region
            y0 = int(r * cell_h)
            y1 = int((r + 1) * cell_h)
            x0 = int(c * cell_w)
            x1 = int((c + 1) * cell_w)

            cell = roi[y0:y1, x0:x1]

            # Min depth in cell = nearest obstacle point
            min_depth = np.min(cell)

            # Encode to braille dot pattern
            frame[pos] = _depth_to_braille(
                min_depth, danger_near, warning_med, attention_far
            )

    return frame


def _depth_to_braille(min_depth, near, med, far):
    """Map a single cell's min depth to a braille dot pattern (6 bits)."""
    if min_depth < near:
        return BRAILLE_ALL_ON   # 0x3F — full block, danger
    elif min_depth < med:
        return BRAILLE_NEAR     # 0x2F — near warning
    elif min_depth < far:
        return BRAILLE_FAR      # 0x09 — light touch
    else:
        return BRAILLE_NONE     # 0x00 — clear


# ═══════════════════════════════════════════════════════════
#  Edge activation → Braille encoding (paper method)
# ═══════════════════════════════════════════════════════════

def edge_cells_to_braille_frame(activated_cells, cols=GRID_COLS, rows=GRID_ROWS):
    """Convert activated grid cells (from edge detection) to a braille frame.

    Args:
        activated_cells: list of (row, col) tuples
        cols, rows: grid dimensions

    Returns:
        frame: uint8 numpy array of shape (FRAME_LEN,)
    """
    frame = np.zeros(FRAME_LEN, dtype=np.uint8)

    for r, c in activated_cells:
        pos = r * cols + c  # firmware position (0-based)
        if 0 <= pos < FRAME_LEN:
            # Bottom rows → stronger obstacle signal (nearer)
            row_ratio = (r + 1) / rows  # 0.2 (top) → 1.0 (bottom)
            frame[pos] = _row_to_braille_pattern(row_ratio)

    return frame


def _row_to_braille_pattern(row_signal):
    """Convert row position signal to braille dot pattern.

    Top rows (far): 2 dots (0x09)
    Mid rows: 4 dots (0x1B or 0x2F)
    Bottom rows (near): all 6 dots (0x3F)
    """
    if row_signal >= 0.8:
        return BRAILLE_ALL_ON   # 0x3F
    elif row_signal >= 0.6:
        return BRAILLE_NEAR     # 0x2F
    elif row_signal >= 0.4:
        return BRAILLE_MEDIUM   # 0x1B
    elif row_signal >= 0.2:
        return BRAILLE_FAR      # 0x09
    else:
        return BRAILLE_NONE     # 0x00


# ═══════════════════════════════════════════════════════════
#  Mode-specific processing
# ═══════════════════════════════════════════════════════════

def apply_rapid_avoid_mode(frame):
    """RAPID_AVOID mode: emphasize near-field obstacles.
    Only pass through cells with strong signals (bottom 3 rows dominant).
    """
    # Bottom 3 rows (positions 6-14, row indices 2-4) at full strength
    # Top 2 rows (positions 0-5) dampened
    for pos in range(FRAME_LEN):
        row = pos // GRID_COLS  # 0-4
        if row < 2:
            frame[pos] = frame[pos] & 0x03  # keep at most 2 dots
    return frame


def apply_local_zoom_mode(frame, depth_map=None, zoom_range_m=1.5):
    """LOCAL_ZOOM mode: only show obstacles within zoom_range_m.
    If depth_map is provided, suppress cells where min_depth > zoom_range_m.
    """
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
                    frame[pos] = BRAILLE_NONE
    return frame


# ═══════════════════════════════════════════════════════════
#  Visualization helpers
# ═══════════════════════════════════════════════════════════

def visualize_frame(frame, cols=GRID_COLS, rows=GRID_ROWS):
    """Render a 15-byte braille frame as an ASCII grid for debugging."""
    patterns = {
        0x3F: "▓", 0x2F: "▄", 0x1B: "▌",
        0x09: "·", 0x00: " ",
    }
    lines = []
    lines.append("┌─────┬─────┬─────┐")
    for r in range(rows):
        line = "│"
        for c in range(cols):
            pos = r * cols + c
            val = frame[pos]
            symbol = patterns.get(val, f"{val:02X}")
            line += f"  {symbol}  │"
        lines.append(line)
        if r < rows - 1:
            lines.append("├─────┼─────┼─────┤")
    lines.append("└─────┴─────┴─────┘")
    return "\n".join(lines)


def braille_to_dot_string(b):
    """Convert a single braille byte to a dot display string: e.g. '0x3F' → '●● / ●● / ●●'"""
    dots = []
    for i in range(3):
        top = "●" if (b >> i) & 1 else "○"
        bot = "●" if (b >> (i + 3)) & 1 else "○"
        dots.append(f"{top}{bot}")
    return " / ".join(dots)
