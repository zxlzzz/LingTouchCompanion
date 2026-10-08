"""Reproduce the actual printed front from the retained finished mesh."""
from pathlib import Path
import argparse
import subprocess
import sys

P = Path(__file__).resolve().parent


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--verify', action='store_true')
    ap.add_argument('--require-baseline', action='store_true', help='Require exact source identity when verifying.')
    args = ap.parse_args()
    def run(name, *extra):
        subprocess.run([sys.executable, '-B', str(P/name), *extra], cwd=P.parent.parent, check=True)
    run('build.py')
    run('export.py')
    if args.verify or args.require_baseline:
        run('verify.py', *(['--require-baseline'] if args.require_baseline else []))


if __name__ == '__main__':
    main()
