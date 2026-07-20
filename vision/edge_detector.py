"""
Edge/contour-based vision pipeline — lightweight alternative.

Replicates the method from:
  Teng et al., "Seeing with the Hands", CHI '25
  Section 4.2 Implementation, Figure 3(d)

Pipeline:
  RGB → Grayscale → Binary threshold → Gaussian blur →
  Canny edge detection → Contour filter (>min_area) →
  Polygon approximation → Grid projection

This is the primary fallback when Depth Anything V2 is too heavy
for the target hardware. Runs at 15+ FPS even on Raspberry Pi Zero 2.

Usage:
  from edge_detector import EdgePipeline
  pipe = EdgePipeline(grid_cols=3, grid_rows=5)
  activated_cells = pipe.process(bgr_frame)
  # activated_cells: list of (row, col) tuples
"""

import cv2
import numpy as np


class EdgePipeline:
    """Contour-based obstacle detection (CHI '25 paper method, adapted)."""

    def __init__(
        self,
        grid_cols=3,
        grid_rows=5,
        binary_threshold=90,
        gaussian_kernel=(5, 5),
        canny_low=50,
        canny_high=150,
        min_contour_area=1000,
        roi_top_ratio=0.15,
        roi_bottom_ratio=0.05,
    ):
        self.grid_cols = grid_cols
        self.grid_rows = grid_rows
        self.binary_threshold = binary_threshold
        self.gaussian_kernel = gaussian_kernel
        self.canny_low = canny_low
        self.canny_high = canny_high
        self.min_contour_area = min_contour_area
        self.roi_top = roi_top_ratio
        self.roi_bottom = roi_bottom_ratio

    def process(self, bgr_frame, return_debug=False):
        """Process a BGR frame and return activated grid cells.

        Args:
            bgr_frame: numpy array (H, W, 3) uint8 BGR
            return_debug: if True, also return intermediate images for visualization

        Returns:
            activated_cells: list of (row, col) tuples, 0-indexed
            debug_dict (if return_debug): dict with 'gray', 'binary', 'edges', 'grid'
        """
        h, w = bgr_frame.shape[:2]

        # ── Step 1: Crop ROI ────────────────────────────
        y_start = int(h * self.roi_top)
        y_end = int(h * (1.0 - self.roi_bottom))
        roi = bgr_frame[y_start:y_end, :]

        # ── Step 2: Grayscale + Binary Threshold ─────────
        gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
        _, binary = cv2.threshold(
            gray, self.binary_threshold, 255, cv2.THRESH_BINARY
        )

        # ── Step 3: Gaussian Blur ────────────────────────
        blurred = cv2.GaussianBlur(binary, self.gaussian_kernel, 0)

        # ── Step 4: Canny Edge Detection ─────────────────
        edges = cv2.Canny(blurred, self.canny_low, self.canny_high)

        # ── Step 5: Find & Filter Contours ───────────────
        contours, _ = cv2.findContours(
            edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
        )
        filtered = [c for c in contours if cv2.contourArea(c) > self.min_contour_area]

        # ── Step 6: Polygon Approximation ────────────────
        approx_contours = []
        for c in filtered:
            peri = cv2.arcLength(c, True)
            approx = cv2.approxPolyDP(c, 0.02 * peri, True)
            approx_contours.append(approx)

        # ── Step 7: Grid Projection ──────────────────────
        activated = self._project_grid(roi, approx_contours)

        if return_debug:
            debug = self._draw_debug(roi, approx_contours, activated)
            debug["gray"] = gray
            debug["binary"] = binary
            debug["edges"] = edges
            return activated, debug

        return activated

    def _project_grid(self, roi, contours):
        """Project a grid onto the image and check which cells contain contours.

        Each cell is checked: if any contour point falls inside it, the cell is activated.
        """
        h, w = roi.shape[:2]
        cell_w = w / self.grid_cols
        cell_h = h / self.grid_rows
        activated_set = set()

        for c in contours:
            for point in c:
                px, py = point[0]  # OpenCV contour point format
                col = int(px / cell_w)
                row = int(py / cell_h)
                col = max(0, min(col, self.grid_cols - 1))
                row = max(0, min(row, self.grid_rows - 1))
                activated_set.add((row, col))

        # Return sorted by firmware position order (row-major, top-to-bottom, left-to-right)
        activated = sorted(activated_set, key=lambda rc: rc[0] * self.grid_cols + rc[1])
        return activated

    def _draw_debug(self, roi, contours, activated):
        """Draw grid overlay and contours for debugging."""
        h, w = roi.shape[:2]
        canvas = roi.copy()

        # Draw contours in green
        cv2.drawContours(canvas, contours, -1, (0, 255, 0), 2)

        # Draw grid lines in blue
        cell_w, cell_h = w / self.grid_cols, h / self.grid_rows
        for i in range(1, self.grid_cols):
            x = int(i * cell_w)
            cv2.line(canvas, (x, 0), (x, h), (255, 0, 0), 1)
        for j in range(1, self.grid_rows):
            y = int(j * cell_h)
            cv2.line(canvas, (0, y), (w, y), (255, 0, 0), 1)

        # Highlight activated cells in red
        activated_set = set(activated)
        for row in range(self.grid_rows):
            for col in range(self.grid_cols):
                if (row, col) in activated_set:
                    x1 = int(col * cell_w)
                    y1 = int(row * cell_h)
                    x2 = int((col + 1) * cell_w)
                    y2 = int((row + 1) * cell_h)
                    overlay = canvas.copy()
                    cv2.rectangle(overlay, (x1, y1), (x2, y2), (0, 0, 255), -1)
                    cv2.addWeighted(overlay, 0.3, canvas, 0.7, 0, canvas)

        return {"grid": canvas, "contours": contours, "activated": activated}
