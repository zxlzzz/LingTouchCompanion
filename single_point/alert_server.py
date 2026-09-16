"""Compatibility entry point for the single-point paper experiment condition."""

import sys
from pathlib import Path

VISIONSS_DIR = Path(__file__).resolve().parent.parent / "visionss"
if str(VISIONSS_DIR) not in sys.path:
    sys.path.insert(0, str(VISIONSS_DIR))

from experiment_server import main  # noqa: E402


if __name__ == "__main__":
    main(default_condition="single_point", default_port=8761)
