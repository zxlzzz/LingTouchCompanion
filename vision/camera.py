"""
Camera capture module — USB camera with optional image file fallback.

Supports:
  - USB webcam via OpenCV (default)
  - Image file / directory for testing with saved frames
  - Test data loading from vision/data/

Usage:
  from camera import USBCamera, FileSource
  cam = USBCamera(index=0, width=640, height=480)
  frame = cam.read()  # returns BGR numpy array

Reference: CHI '25 "Seeing with the Hands" — camera at 15 FPS, 640×480
"""

import cv2
import os
import time
from pathlib import Path


class CameraSource:
    """Abstract camera source interface."""

    def read(self):
        """Return (BGR frame, timestamp) or (None, None) on failure."""
        raise NotImplementedError

    def release(self):
        raise NotImplementedError


class USBCamera(CameraSource):
    """USB webcam capture via OpenCV VideoCapture."""

    def __init__(self, index=0, width=640, height=480, fps=15):
        self.index = index
        self.width = width
        self.height = height
        self.fps = fps
        self._cap = None
        self._frame_interval = 1.0 / fps
        self._last_frame_time = 0

    def open(self):
        """Open camera device. Returns True on success."""
        self._cap = cv2.VideoCapture(self.index)
        if not self._cap.isOpened():
            return False
        self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        self._cap.set(cv2.CAP_PROP_FPS, self.fps)
        return True

    def read(self):
        if self._cap is None:
            return None, None
        now = time.time()
        if now - self._last_frame_time < self._frame_interval:
            time.sleep(self._frame_interval - (now - self._last_frame_time))
        ret, frame = self._cap.read()
        self._last_frame_time = time.time()
        if not ret:
            return None, None
        return frame, self._last_frame_time

    def release(self):
        if self._cap is not None:
            self._cap.release()
            self._cap = None


class FileSource(CameraSource):
    """Read frames from image files (for testing/development).

    Supports:
      - Single image: loops same image
      - Directory: iterates .jpg/.png files sorted by name
    """

    def __init__(self, path, loop=True):
        self.loop = loop
        self._files = []
        p = Path(path)
        if p.is_dir():
            self._files = sorted(
                p.glob("*.jpg") + p.glob("*.jpeg") + p.glob("*.png")
            )
        elif p.is_file():
            self._files = [p]
        else:
            raise FileNotFoundError(f"Image source not found: {path}")
        self._idx = 0
        self._done = False

    def read(self):
        if self._done:
            return None, None
        fp = self._files[self._idx]
        frame = cv2.imread(str(fp))
        if frame is None:
            return None, None
        self._idx += 1
        if self._idx >= len(self._files):
            if self.loop:
                self._idx = 0
            else:
                self._done = True
        return frame, time.time()

    def release(self):
        self._files.clear()
        self._done = True


def load_test_frame(name=""):
    """Load a test image from vision/data/ directory."""
    data_dir = Path(__file__).parent / "data"
    if name:
        fp = data_dir / name
        if fp.exists():
            return cv2.imread(str(fp))
    # Return first image found
    for ext in ("*.jpg", "*.jpeg", "*.png"):
        files = sorted(data_dir.glob(ext))
        if files:
            return cv2.imread(str(files[0]))
    return None
