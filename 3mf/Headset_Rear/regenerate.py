"""Rebuild the final rear from the retained anatomical inputs."""
from pathlib import Path
import subprocess
import sys
P=Path(__file__).resolve().parent
if __name__ == '__main__':
    for path in [P.parent/'Headset_Inputs/prepare.py',P/'build.py',P/'revised/build.py',P/'revised/export.py']:
        subprocess.run([sys.executable,'-B',str(path)],cwd=P.parent,check=True)
