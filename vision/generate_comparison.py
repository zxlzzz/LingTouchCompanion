"""
Generate a clean comparison page: Original → Depth Heatmap → Braille Grid.
Uses HTML tables for braille grids — no Unicode font dependencies.
"""
import cv2
import numpy as np
import sys
import os
import json
import base64
from pathlib import Path

# Add parent dir to path
sys.path.insert(0, os.path.dirname(__file__))

from depth_estimator import DepthEstimator, SimpleDepthEstimator
from grid_mapper import depth_map_to_dot_frame, depth_map_to_xy_frame
from config import GRID_COLS, GRID_ROWS, FRAME_LEN

DATA_DIR = Path(__file__).parent / "data"
OUT_DIR = DATA_DIR / "compare"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Test images
IMAGES = [
    DATA_DIR / "real/indoor2.jpg",
    DATA_DIR / "real/indoor3.jpg",
    DATA_DIR / "real/indoor4.jpg",
    DATA_DIR / "real/indoor5.jpg",
    DATA_DIR / "test_indoor.jpg",
    DATA_DIR / "scene_indoor.jpg",
]


def encode_img(img_bgr):
    """Encode BGR image to base64 JPEG data URI."""
    _, buf = cv2.imencode(".jpg", img_bgr, [cv2.IMWRITE_JPEG_QUALITY, 75])
    b64 = base64.b64encode(buf).decode()
    return f"data:image/jpeg;base64,{b64}"


def depth_to_heatmap(depth_map):
    """Convert depth map to BGR heatmap for display."""
    d = depth_map.copy()
    d_min, d_max = d.min(), d.max()
    if d_max - d_min > 1e-6:
        d = (d - d_min) / (d_max - d_min)
    else:
        d = np.zeros_like(d)
    d = (d * 255).astype(np.uint8)
    heat = cv2.applyColorMap(d, cv2.COLORMAP_INFERNO)
    return heat


def render_grid_html(frame):
    """Render 9x10 SMA-dot frame as an HTML table.
    Each cell = one SMA dot. Green = on, dark = off."""
    rows_html = []
    for r in range(GRID_ROWS):
        cells_html = []
        for c in range(GRID_COLS):
            pos = r * GRID_COLS + c
            val = int(frame[pos])
            cls = "sma on" if val else "sma off"
            cells_html.append(f'<td class="{cls}"></td>')
        rows_html.append(f'<tr>{"".join(cells_html)}</tr>')
    table = f'<table class="braillegrid"><tbody>{"".join(rows_html)}</tbody></table>'
    return table


def process_image(img_path, estimator):
    """Process one image and return results."""
    frame = cv2.imread(str(img_path))
    if frame is None:
        print(f"  SKIP: cannot read {img_path}")
        return None

    h, w = frame.shape[:2]
    if w > 640:
        frame = cv2.resize(frame, (640, int(640 * h / w)))
    print(f"  Processing {img_path.name} ({frame.shape[1]}x{frame.shape[0]})...")

    depth_map = estimator.estimate(frame)
    xy_frame = depth_map_to_xy_frame(depth_map)
    im_frame = depth_map_to_dot_frame(depth_map)

    original_b64 = encode_img(frame)
    heatmap_bgr = depth_to_heatmap(depth_map)
    heatmap_b64 = encode_img(heatmap_bgr)
    xy_grid_html = render_grid_html(xy_frame)
    im_grid_html = render_grid_html(im_frame)
    return {
        "name": img_path.stem,
        "original": original_b64,
        "heatmap": heatmap_b64,
        "xy_grid": xy_grid_html,
        "xy_active": int(xy_frame.sum()),
        "im_grid": im_grid_html,
        "im_active": int(im_frame.sum()),
    }


CSS = """
*{margin:0;padding:0;box-sizing:border-box}
body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;background:#0d1117;color:#c9d1d9;padding:24px}
h1{color:#58a6ff;margin-bottom:8px;font-size:22px}
h2{color:#f0883e;margin:28px 0 12px 0;font-size:18px;border-bottom:1px solid #30363d;padding-bottom:6px}
p.note{color:#8b949e;font-size:13px;margin-bottom:20px}
.row{display:flex;gap:20px;margin-bottom:16px;align-items:flex-start;flex-wrap:wrap}
.col{text-align:center}
.col img{max-width:300px;border:1px solid #30363d;border-radius:4px}
.col .label{color:#8b949e;font-size:13px;margin-bottom:6px}

/* 9x10 SMA dot grid */
table.braillegrid{border-collapse:collapse;margin:0 auto;font-size:0}
table.braillegrid td.sma{width:16px;height:16px;border:1px solid #1a1f26;padding:0}
table.braillegrid td.sma.on{background:#3fb950}
table.braillegrid td.sma.off{background:#161b22}

pre.hexdump{color:#58a6ff;font-size:10px;margin-top:6px;font-family:monospace;max-width:300px;word-break:break-all}
"""


def build_html(results):
    """Build full comparison HTML page."""
    sections = []
    for r in results:
        if r is None:
            continue
        sections.append(f"""
<h2>{r['name']}</h2>
<div class="row">
  <div class="col">
    <div class="label">Original</div>
    <img src="{r['original']}" alt="original">
  </div>
  <div class="col">
    <div class="label">Depth Heatmap</div>
    <img src="{r['heatmap']}" alt="depth heatmap">
  </div>
  <div class="col">
    <div class="label">XY Projection (3D→ground plane) — {r['xy_active']}/90 activated</div>
    {r['xy_grid']}
  </div>
  <div class="col">
    <div class="label">Image-plane — {r['im_active']}/90 activated</div>
    {r['im_grid']}
  </div>
</div>""")

    html = f"""<!DOCTYPE html>
<html lang="zh"><head><meta charset="utf-8"><title>LingTouch Vision Comparison</title>
<style>{CSS}</style></head><body>
<h1>Depth Mode Comparison — Original / Heatmap / SMA Dot Grid (9×10)</h1>
<p class="note">Each cell = one SMA dot (90 total = 15 modules × 6 dots). Green = activated (obstacle), dark = clear.
Bottom rows = near field, top rows = far field. Depth Anything V2, dual-threshold + bottom penalty.</p>
{''.join(sections)}
</body></html>"""

    out_path = OUT_DIR / "index.html"
    out_path.write_text(html, encoding="utf-8")
    print(f"\nWrote {out_path} ({len(html)} bytes)")


def main():
    print("=" * 60)
    print("Loading Depth Anything V2 model...")
    try:
        estimator = DepthEstimator(model_size="small", use_gpu=False)
        estimator.load()
    except Exception as e:
        print(f"Model load failed: {e}")
        print("Falling back to SimpleDepthEstimator.")
        estimator = SimpleDepthEstimator()

    results = []
    for img_path in IMAGES:
        if img_path.exists():
            r = process_image(img_path, estimator)
            results.append(r)
        else:
            print(f"  SKIP: {img_path} not found")

    print(f"\nProcessed {len(results)} images.")
    build_html(results)
    print("Done. Open vision/data/compare/index.html in a browser.")


if __name__ == "__main__":
    main()
