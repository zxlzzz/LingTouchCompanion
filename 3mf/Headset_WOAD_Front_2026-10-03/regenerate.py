"""Rebuild the retained final front and rear, including their source dependencies."""
from pathlib import Path
import subprocess
import sys
P=Path(__file__).resolve().parent
if __name__ == '__main__':
    subprocess.run([sys.executable,'-B',str(P.parent/'Headset_Rear/regenerate.py')],check=True)
    subprocess.run([sys.executable,'-B',str(P/'camera_mount/regenerate.py'),*sys.argv[1:]],check=True)
