"""Rebuild all retained front, rear and two-object handle models."""
from pathlib import Path
import subprocess
import sys

P = Path(__file__).resolve().parent

if __name__ == '__main__':
    for entry in [P/'Headset_WOAD_Front_2026-10-03/regenerate.py', P/'Handle/regenerate.py']:
        subprocess.run([sys.executable, '-B', str(entry), *sys.argv[1:]], check=True)
