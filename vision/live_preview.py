"""
Live preview — webcam → depth → 9×10 SMA dot grid.
Press Q to quit, S to toggle SMA grid size.
"""
import cv2
import numpy as np
import sys
import os
import time

sys.path.insert(0, os.path.dirname(__file__))

from depth_estimator import DepthEstimator
from grid_mapper import depth_map_to_dot_frame
from config import GRID_COLS, GRID_ROWS, FRAME_LEN, ROI_TOP_RATIO, ROI_BOTTOM_RATIO


def depth_to_heatmap(depth_map):
    d = depth_map.copy()
    d_min, d_max = d.min(), d.max()
    if d_max - d_min > 1e-6:
        d = (d - d_min) / (d_max - d_min)
    else:
        d = np.zeros_like(d)
    d = (d * 255).astype(np.uint8)
    return cv2.applyColorMap(d, cv2.COLORMAP_INFERNO)


def render_dot_grid(frame_flat, cell_size=20):
    """Render 9x10 SMA dot grid as an image."""
    h, w = GRID_ROWS * cell_size, GRID_COLS * cell_size
    img = np.zeros((h, w, 3), dtype=np.uint8)
    grid = frame_flat.reshape(GRID_ROWS, GRID_COLS)
    for r in range(GRID_ROWS):
        for c in range(GRID_COLS):
            y0, y1 = r * cell_size, (r + 1) * cell_size
            x0, x1 = c * cell_size, (c + 1) * cell_size
            color = (0, 220, 80) if grid[r, c] else (20, 25, 30)
            cv2.rectangle(img, (x0, y0), (x1 - 1, y1 - 1), color, -1)
    # Row labels (bottom = near)
    for r in range(GRID_ROWS):
        cv2.putText(img, str(r), (GRID_COLS * cell_size + 2, (r + 1) * cell_size - 5),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.3, (150, 150, 150), 1)
    return img


def main(camera_source=0):
    """camera_source: webcam index (int) or IP webcam URL (str).
    For Android phone:
      1. Install 'IP Webcam' from Play Store
      2. Start server on phone (same WiFi as PC)
      3. Run: python live_preview.py http://<phone-ip>:8080/video
    """
    print("Loading Depth Anything V2 model...")
    estimator = DepthEstimator(model_size="small", use_gpu=False)
    estimator.load()

    cap = cv2.VideoCapture(camera_source)
    if not cap.isOpened():
        print(f"Cannot open camera source: {camera_source}")
        return

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

    cell_size = 20
    show_roi_overlay = True
    fps_smooth = 0

    print("Live preview started. Q=quit, S=dot size, R=toggle ROI overlay")
    print(f"Grid: {GRID_COLS}x{GRID_ROWS} = {FRAME_LEN} SMA dots")

    while True:
        t0 = time.time()
        ret, frame = cap.read()
        if not ret:
            break

        h, w = frame.shape[:2]
        if w > 640:
            frame = cv2.resize(frame, (640, int(640 * h / w)))

        depth_map = estimator.estimate(frame)
        braille = depth_map_to_dot_frame(depth_map)
        active = int(braille.sum())

        # Build display
        heatmap = depth_to_heatmap(depth_map)
        dot_img = render_dot_grid(braille, cell_size)

        # ROI overlay on original
        disp_frame = frame.copy()
        if show_roi_overlay:
            h_f, w_f = disp_frame.shape[:2]
            y0_roi = int(h_f * ROI_TOP_RATIO)
            y1_roi = int(h_f * (1.0 - ROI_BOTTOM_RATIO))
            cv2.rectangle(disp_frame, (0, y0_roi), (w_f, y1_roi), (0, 255, 255), 1)

        # FPS
        dt = time.time() - t0
        fps_smooth = 0.9 * fps_smooth + 0.1 * (1.0 / max(dt, 0.001))

        # Status line on dot grid
        status = f"{active}/{FRAME_LEN} activated | {fps_smooth:.1f} FPS"
        dot_display = dot_img.copy()
        cv2.putText(dot_display, status, (4, 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, (200, 200, 200), 1)

        # Side-by-side layout
        pad_left = dot_display.shape[1]

        # Scale heatmap to match combined height
        target_h = max(disp_frame.shape[0], dot_display.shape[0])
        dot_padded = np.zeros((target_h, pad_left, 3), dtype=np.uint8)
        dot_padded[:dot_display.shape[0], :dot_display.shape[1]] = dot_display

        heat_resized = cv2.resize(heatmap, (heatmap.shape[1], target_h))
        disp_resized = cv2.resize(disp_frame, (disp_frame.shape[1], target_h))

        combined = np.hstack([disp_resized, heat_resized, dot_padded])

        # Handle window resize
        screen_h = 1080
        if combined.shape[0] > screen_h - 100:
            scale = (screen_h - 100) / combined.shape[0]
            combined = cv2.resize(combined, None, fx=scale, fy=scale)

        cv2.imshow("LingTouch Live Preview | Original · Heatmap · SMA Grid", combined)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('s'):
            cell_size = 30 if cell_size == 20 else (40 if cell_size == 30 else 20)
        elif key == ord('r'):
            show_roi_overlay = not show_roi_overlay

    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="LingTouch live preview")
    parser.add_argument("camera", nargs="?", default="0",
                        help="Webcam index (0, 1, ...) or IP webcam URL (http://...)")
    args = parser.parse_args()
    try:
        source = int(args.camera)
    except ValueError:
        source = args.camera

    if isinstance(source, str):
        print(f"Connecting to IP camera: {source}")
    main(source)
