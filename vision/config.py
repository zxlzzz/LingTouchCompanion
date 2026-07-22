"""
LingTouch Companion — Vision Pipeline Configuration

Camera → Depth Estimation → Grid Mapping → Braille Frame
"""

# ── Camera ──────────────────────────────────────────────
CAMERA_INDEX = 0            # USB camera device index
CAMERA_WIDTH = 640
CAMERA_HEIGHT = 480
CAMERA_FPS = 15

# ── Depth Anything V2 ──────────────────────────────────
DEPTH_MODEL_SIZE = "small"  # "small" | "base" | "large"
# small: ~25M params, best for RPi 4/5
# base:  ~98M params, balanced
# large: ~335M params, best accuracy but needs GPU
DEPTH_INPUT_SIZE = (518, 518)  # model input resolution
USE_GPU = False             # True for CUDA, False for CPU (RPi default)

# ── Grid mapping ───────────────────────────────────────
# 9 cols × 10 rows = 90 cells = 15 modules × 6 SMA dots per module
# Each cell maps to one SMA dot (on/off)
GRID_COLS = 9               # horizontal: 9 SMA dot columns
GRID_ROWS = 10              # vertical: 10 SMA dot rows (top=farther → bottom=nearer)

# Region of Interest for image-plane pipeline
# (ignore sky at top, feet at bottom)
ROI_TOP_RATIO = 0.2
ROI_BOTTOM_RATIO = 0.1

# ── XY Ground-plane projection ──────────────────────────
# Camera
CAM_HEIGHT_M = 1.20         # camera height above ground (meters)
CAM_FOV_H_DEG = 65          # horizontal field of view (degrees)
GROUND_CLEARANCE_M = 0.10   # obstacle = point is above ground + clearance (meters)

# XY grid cell size
XY_CELL_M = 0.50            # 50cm × 50cm per cell
XY_Y_NEAR_M = 0.3           # nearest forward distance
# XY_Y_FAR derived: XY_Y_NEAR + GRID_ROWS × XY_CELL_M
# X range derived: ±0.5 × GRID_COLS × XY_CELL_M

# ── Obstacle detection ──
CELL_OBS_PERCENTILE = 85
MIN_CELL_COVERAGE = 0.30
MAX_ACTIVATIONS = 22        # cap total activated dots (90 total)

# Absolute fallback thresholds (used when depth IS in real meters, e.g. stereo cam)
DANGER_NEAR_M = 0.5
WARNING_MEDIUM_M = 1.0
ATTENTION_FAR_M = 2.0

# ── Braille dot patterns ───────────────────────────────
# Each module: 2 cols × 3 rows of SMA dots, bit0~bit5
# Bit layout (ESP32 convention): bit0=col1-top, bit1=col1-mid, bit2=col1-bot,
#                                bit3=col2-top, bit4=col2-mid, bit5=col2-bot
BRAILLE_ALL_ON  = 0x3F   # ▓▓▓ (all 6 dots)
BRAILLE_NEAR    = 0x2F   # dots: col1-bot, col2-all (bottom-heavy warning)
BRAILLE_MEDIUM  = 0x1B   # dots: col1-all, col2-mid
BRAILLE_FAR     = 0x09   # dots: col1-mid, col2-top (light touch)
BRAILLE_NONE    = 0x00   # clear

# ── Dual-mode thresholds ───────────────────────────────
# MODE_RAPID_AVOID: fast obstacle detection, wider FOV
RAPID_AVOID_STEP_MS = 100       # frame interval

# MODE_LOCAL_ZOOM: detailed near-field, narrower FOV
LOCAL_ZOOM_RANGE_M = 1.5        # only show obstacles within 1.5m
LOCAL_ZOOM_STEP_MS = 200        # frame interval

# ── Alternative: Edge-based pipeline (paper method) ────
# Lightweight fallback when Depth Anything is too heavy
EDGE_BINARY_THRESHOLD = 90      # grayscale → binary threshold
EDGE_GAUSSIAN_KERNEL = (5, 5)   # blur kernel
EDGE_CANNY_LOW = 50
EDGE_CANNY_HIGH = 150
EDGE_MIN_CONTOUR_AREA = 1000    # px², paper used 1000 for 640×480

# ── Output ─────────────────────────────────────────────
# Serial to ESP32 (UART)
SERIAL_PORT = "/dev/ttyUSB0"  # or /dev/serial0 for RPi GPIO UART
SERIAL_BAUDRATE = 115200

# Frame format: 90 bytes, one per SMA dot (9 cols × 10 rows)
# Each byte: 0 or 1 (single dot on/off)
FRAME_LEN = 90
