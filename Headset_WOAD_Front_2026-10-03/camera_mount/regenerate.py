"""Rebuild all front prerequisites and the retained CS30-slot final."""
from pathlib import Path
import argparse
import subprocess
import sys

P=Path(__file__).resolve().parent

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--rebuild-inputs',action='store_true', help='Retessellate the customer STEP; requires cadquery-ocp.')
    ap.add_argument('--verify',action='store_true')
    ap.add_argument('--slice',action='store_true')
    ap.add_argument('--render',action='store_true')
    args=ap.parse_args()
    def run(name,*extra):subprocess.run([sys.executable,'-B',str(P/name),*extra],cwd=P.parent.parent,check=True)
    run('../../Headset_Inputs/prepare.py')
    run('../../Headset_Rear/build.py')
    if args.rebuild_inputs:run('../camera_source.py')
    run('../revised/build.py')
    run('../structural/build.py')
    run('build.py');run('export.py')
    if args.verify:run('verify.py')
    if args.slice:run('slice.py')
    if args.render:run('render.py','--samples','16','--width','1200','--no-comparison')

if __name__=='__main__':main()
