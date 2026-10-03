"""Rebuild the separately saved revision without rewriting prior deliverables.

Install the requirements in the parent folder, then run this file from a clean
checkout. --verify checks head/camera fit, --render regenerates the comparison
plates, and --check-import uses the installed Bambu importer without slicing.
"""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys

P=Path(__file__).resolve().parent
BASE=P.parent
ROOT=BASE.parent
REAR=ROOT/'Headset_Rear/revised'

def run(path,*args):subprocess.run([sys.executable,'-B',str(path),*args],cwd=ROOT,check=True)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--verify',action='store_true')
    ap.add_argument('--render',action='store_true')
    ap.add_argument('--check-import',action='store_true')
    args=ap.parse_args()
    for name,row in json.loads((ROOT/'Headset_Inputs/input_manifest.json').read_text('utf8')).items():
        data=(ROOT/'Headset_Inputs'/name).read_bytes()
        assert hashlib.sha256(data).hexdigest()==row['sha256'] and len(data)==row['bytes'],name
    before={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest()
            for path in ROOT.glob('Headset_*/*.3mf')}
    run(REAR/'build.py');run(REAR/'export.py')
    run(P/'build.py');run(P/'export.py')
    if args.verify:run(P/'verify.py')
    if args.render:run(P/'render.py','--samples','32','--width','1200')
    if args.check_import:run(REAR/'check_import.py');run(P/'check_import.py')
    assert all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==sha for name,sha in before.items())
    print('Separately saved revision rebuilt. Every preceding 3MF is unchanged.',flush=True)

if __name__=='__main__':main()
