#!/usr/bin/env python3
"""
LingTouch Companion — Vision Pipeline Entry Point

Camera → Depth Estimation / Edge Detection → Grid Mapping → Braille Frame → Output

Usage:
  # Depth-based (primary, requires PyTorch + Depth Anything V2)
  python main.py --mode depth --camera 0 --output serial

  # Edge-based (lightweight fallback, runs on any hardware)
  python main.py --mode edge --camera 0 --output serial

  # Test with image file
  python main.py --mode edge --image path/to/test.jpg --output file

  # Visual debug window
  python main.py --mode edge --camera 0 --debug

Reference:
  Depth mode: Depth Anything V2 monocular depth estimation
  Edge mode:  CHI '25 "Seeing with the Hands" contour-based method (Teng et al.)

Architecture:
  ┌──────────┐     ┌──────────────┐     ┌───────────┐     ┌──────────┐
  │  Camera  │────▶│  Processor   │────▶│  Mapper   │────▶│  Sender  │
  │ (USB/RPi)│     │ depth/edge   │     │ depth→grid│     │serial/   │
  └──────────┘     └──────────────┘     └───────────┘     │BLE/file  │
                                                           └──────────┘
"""

import argparse
import sys
import time
import signal
import numpy as np

from camera import USBCamera, FileSource
from depth_estimator import DepthEstimator, SimpleDepthEstimator
from edge_detector import EdgePipeline
from grid_mapper import (
    depth_map_to_braille_frame,
    edge_cells_to_braille_frame,
    apply_rapid_avoid_mode,
    apply_local_zoom_mode,
    visualize_frame,
)
from output_sender import create_sender
from config import (
    FRAME_LEN,
    RAPID_AVOID_STEP_MS,
    LOCAL_ZOOM_STEP_MS,
)

# Global flag for graceful shutdown
_running = True


def signal_handler(sig, frame):
    global _running
    _running = False
    print("\n[Vision] Shutting down...")


signal.signal(signal.SIGINT, signal_handler)
signal.signal(signal.SIGTERM, signal_handler)


# ═══════════════════════════════════════════════════════════
#  Pipeline runners
# ═══════════════════════════════════════════════════════════

def run_depth_pipeline(camera, sender, mode="rapid_avoid", debug=False):
    """Depth Anything V2 pipeline."""
    print("[Vision] Initializing Depth Anything V2 pipeline...")
    try:
        estimator = DepthEstimator(model_size="small", use_gpu=False)
        estimator.load()
    except Exception as e:
        print(f"[Vision] Depth model load failed: {e}")
        print("[Vision] Falling back to SimpleDepthEstimator (heuristic).")
        estimator = SimpleDepthEstimator()

    step_ms = RAPID_AVOID_STEP_MS if mode == "rapid_avoid" else LOCAL_ZOOM_STEP_MS
    print(f"[Vision] Depth pipeline running. Mode={mode}. Ctrl+C to stop.")

    while _running:
        frame_bgr, ts = camera.read()
        if frame_bgr is None:
            print("[Vision] Camera read failed, retrying...")
            time.sleep(0.5)
            continue

        # Depth estimation
        depth_map = estimator.estimate(frame_bgr)

        # Depth → braille frame
        braille = depth_map_to_braille_frame(depth_map)

        # Apply mode-specific processing
        if mode == "rapid_avoid":
            braille = apply_rapid_avoid_mode(braille)
        elif mode == "local_zoom":
            braille = apply_local_zoom_mode(braille, depth_map)

        # Send
        if sender:
            sender.send(braille)

        # Debug display
        if debug:
            print(f"\r[Vision] Frame @ {ts:.1f}  ", end="")
            print(visualize_frame(braille))

        # Frame rate control
        elapsed = (time.time() - ts) * 1000
        sleep_ms = max(1, step_ms - elapsed)
        time.sleep(sleep_ms / 1000.0)


def run_edge_pipeline(camera, sender, mode="rapid_avoid", debug=False):
    """Edge/contour-based pipeline (CHI '25 paper method)."""
    print("[Vision] Initializing edge-detection pipeline...")
    pipe = EdgePipeline()

    step_ms = RAPID_AVOID_STEP_MS if mode == "rapid_avoid" else LOCAL_ZOOM_STEP_MS
    print(f"[Vision] Edge pipeline running. Mode={mode}. Ctrl+C to stop.")

    while _running:
        frame_bgr, ts = camera.read()
        if frame_bgr is None:
            print("[Vision] Camera read failed, retrying...")
            time.sleep(0.5)
            continue

        # Edge detection + grid projection
        if debug:
            activated, debug_data = pipe.process(frame_bgr, return_debug=True)
        else:
            activated = pipe.process(frame_bgr)

        # Edge cells → braille frame
        braille = edge_cells_to_braille_frame(activated)

        # Send
        if sender:
            sender.send(braille)

        # Debug display
        if debug:
            print(f"\r[Vision] Frame @ {ts:.1f}  activated={len(activated)} cells  ", end="")
            print(debug_data)

        # Frame rate control
        elapsed = (time.time() - ts) * 1000
        sleep_ms = max(1, step_ms - elapsed)
        time.sleep(sleep_ms / 1000.0)


# ═══════════════════════════════════════════════════════════
#  Test mode: single image
# ═══════════════════════════════════════════════════════════

def run_single_test(image_path, use_depth=False):
    """Process a single image and print the braille frame."""
    import cv2

    frame = cv2.imread(image_path)
    if frame is None:
        print(f"[Vision] Cannot read image: {image_path}")
        return

    print(f"[Vision] Processing: {image_path} ({frame.shape[1]}×{frame.shape[0]})")

    if use_depth:
        try:
            estimator = DepthEstimator(model_size="small", use_gpu=False)
            estimator.load()
        except Exception as e:
            print(f"[Vision] Real model unavailable: {e}")
            print("[Vision] Falling back to SimpleDepthEstimator.")
            estimator = SimpleDepthEstimator()
        depth_map = estimator.estimate(frame)
        braille = depth_map_to_braille_frame(depth_map)
    else:
        pipe = EdgePipeline()
        activated = pipe.process(frame)
        braille = edge_cells_to_braille_frame(activated)
        print(f"  Activated cells: {activated}")

    print("\n  Braille Frame (hex):")
    print(f"  {' '.join(f'{b:02X}' for b in braille)}")
    print()
    print(visualize_frame(braille))


# ═══════════════════════════════════════════════════════════
#  CLI
# ═══════════════════════════════════════════════════════════

def main():
    parser = argparse.ArgumentParser(
        description="LingTouch Companion — Vision Pipeline"
    )
    parser.add_argument(
        "--mode", choices=["depth", "edge"], default="edge",
        help="Vision processing mode: depth (Depth Anything V2) or edge (paper method)"
    )
    parser.add_argument(
        "--device-mode", choices=["rapid_avoid", "local_zoom"],
        default="rapid_avoid",
        help="Device operating mode (matches ESP32: MODE_RAPID_AVOID / MODE_LOCAL_ZOOM)"
    )
    parser.add_argument(
        "--camera", type=int, default=0,
        help="USB camera device index (default: 0)"
    )
    parser.add_argument(
        "--image", type=str, default=None,
        help="Single image path for testing (bypasses live camera)"
    )
    parser.add_argument(
        "--output", choices=["serial", "file", "http", "network", "none"],
        default="none",
        help="Output method (default: none = print only)"
    )
    parser.add_argument(
        "--serial-port", default="/dev/ttyUSB0",
        help="Serial port for ESP32 (default: /dev/ttyUSB0)"
    )
    parser.add_argument(
        "--debug", action="store_true",
        help="Show debug visualization"
    )
    parser.add_argument(
        "--version", action="store_true",
        help="Print version and exit"
    )
    args = parser.parse_args()

    if args.version:
        print("LingTouch Companion — Vision Pipeline v1.0.0")
        return

    # ── Test mode: single image ──────────────────────────
    if args.image:
        run_single_test(args.image, use_depth=(args.mode == "depth"))
        return

    # ── Live camera mode ─────────────────────────────────
    camera = USBCamera(index=args.camera)
    if not camera.open():
        print(f"[Vision] Failed to open camera {args.camera}")
        # Fallback: try FileSource with test data
        try:
            camera = FileSource("vision/data")
            print("[Vision] Using file source for testing.")
        except FileNotFoundError:
            print("[Vision] No data directory. Exiting.")
            sys.exit(1)

    sender = create_sender(
        args.output,
        port=args.serial_port if args.output == "serial" else None,
    )

    try:
        if args.mode == "depth":
            run_depth_pipeline(camera, sender, args.device_mode, args.debug)
        else:
            run_edge_pipeline(camera, sender, args.device_mode, args.debug)
    finally:
        if sender:
            sender.close()
        camera.release()
        print("[Vision] Shutdown complete.")


if __name__ == "__main__":
    main()
