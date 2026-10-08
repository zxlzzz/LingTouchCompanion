"""Rebuild the two-part handle from its retained original 3MF."""
from pathlib import Path
import argparse
import subprocess
import sys
P=Path(__file__).resolve().parent


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--verify',action='store_true')
    ap.add_argument('--require-baseline',action='store_true')
    args=ap.parse_args()
    for name in ['build.py','export.py']:
        subprocess.run([sys.executable,'-B',str(P/name)],check=True)
    if args.verify or args.require_baseline:
        subprocess.run([sys.executable,'-B',str(P/'verify.py'),*(['--require-baseline'] if args.require_baseline else [])],check=True)


if __name__=='__main__':main()
