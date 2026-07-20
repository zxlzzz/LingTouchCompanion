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
GRID_COLS = 3               # horizontal: left / center / right
GRID_ROWS = 5               # vertical: far → near (top → bottom)
# Matches the ESP32 firmware physical layout:
#   1  2  3
#   4  5  6
#   7  8  9
#  10 11 12
#  13 14 15

# Region of Interest: crop middle portion of depth map
# (ignore sky at top, feet at bottom)
ROI_TOP_RATIO = 0.2         # skip top 20% (sky/ceiling)
ROI_BOTTOM_RATIO = 0.1      # skip bottom 10% (ground)

# ── Obstacle detection thresholds (meters) ────────────
DANGER_NEAR_M = 0.5         # < 0.5m: all 6 dots raised (urgent stop)
WARNING_MEDIUM_M = 1.0      # 0.5-1.0m: 4 dots raised (caution)
ATTENTION_FAR_M = 2.0       # 1.0-2.0m: 2 dots raised (awareness)
# > 2.0m: no dots (clear path)

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

# Frame format: 15 bytes, one per braille module (position 0-14)
# Each byte: bits 0-5 = braille dot pattern, bits 6-7 reserved
FRAME_LEN = 15
