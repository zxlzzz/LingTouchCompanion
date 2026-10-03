"""Regenerate and verify the current headset from a clean checkout.

Python 3.11: install requirements.txt, then run this file. --render adds the
three comparison views; --slice requires the installed Bambu Studio engine.
Both wearing-reference and single-material, bed-oriented 3MF files are rebuilt.
The original rear 3MF is preserved byte-for-byte while its mesh is rebuilt.
"""
from pathlib import Path
import argparse, hashlib, json, subprocess, sys

P=Path(__file__).resolve().parent;R=P.parent

def run(path,*args):
    print('Running '+str(path.relative_to(R)),flush=True)
    subprocess.run([sys.executable,str(path),*args],cwd=R,check=True)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--render',action='store_true');ap.add_argument('--slice',action='store_true')
    ap.add_argument('--geometry-only',action='store_true',help='Regenerate inputs, rear meshes and both front 3MF files; skip independent audits.')
    args=ap.parse_args()
    raw=R/'Headset_Inputs'
    for name,row in json.loads((raw/'input_manifest.json').read_text('utf8')).items():
        data=(raw/name).read_bytes()
        assert len(data)==row['bytes'] and hashlib.sha256(data).hexdigest()==row['sha256'],name
    rear=R/'Headset_Rear'
    provenance=json.loads((rear/'source_provenance.json').read_text('utf8'))
    for row in provenance['generator_inputs'].values():
        assert hashlib.sha256((rear/row['file']).read_bytes()).hexdigest()==row['source_sha256']
    run(raw/'prepare.py');run(P/'camera_source.py')
    run(rear/'build.py');run(rear/'export.py','--verify-existing')
    run(P/'build.py');run(P/'export.py')
    if not args.geometry_only:
        run(P/'checks/camera_fit.py')
        run(P/'checks/retention_sphere.py')
        for phase in ('distances','classify','slots','measurements'):
            run(P/'checks/head_fit.py','--phase',phase)
        camera=json.loads((P/'checks/camera_fit.json').read_text('utf8'))
        head=json.loads((P/'checks/head_fit.json').read_text('utf8'))
        assert camera['pass']
        sphere=json.loads((P/'checks/retention_sphere.json').read_text('utf8'))
        assert sphere['sampled_enclosed_component'] and not sphere['source_changed_during_run']
        assert head['all_parts_sampled_penetration_within_contact_epsilon']
        assert head['terminal_slots']['all_slot_locations_and_reach_preserved']
    if args.render:run(P/'render.py','--samples','96','--width','1800')
    if args.slice:run(P/'print_check.py')
    print('Current headset regenerated; original rear unchanged.',flush=True)

if __name__=='__main__':main()
