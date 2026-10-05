"""Slice the retained CS30-slot model using its unchanged embedded settings."""
from pathlib import Path
import subprocess
import sys
P=Path(__file__).resolve().parent
if __name__ == '__main__':
    subprocess.run([sys.executable, '-B', str(P.parent/'structural/slice.py'),
        '--archive', str(P/'Front_CS30_Mount_Print.3mf'),
        '--body', str(P/'geometry/front_body.npz'),
        '--posed-mesh', str(P/'geometry/front_print.npz'),
        '--saved-settings', str(P/'project_settings.json'),
        '--angle', '135', '--report', str(P/'checks/slice.json')], check=True)
