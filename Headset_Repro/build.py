"""Rebuild without reading packaged intermediate or finished meshes."""
from pathlib import Path
import argparse, hashlib, json, runpy, shutil, subprocess, sys
import numpy as np
import trimesh

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
FRONT = 'Headset_CompactFront_Review_2026-10-02'
REAR = 'Headset_Carbon6K_FlatBase_Review_2026-10-02'

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('part', choices=['front', 'rear'])
    parser.add_argument('--version', choices=['requested', 'latest'], default='requested',
                        help='requested reproduces the 72.02/20.55 cm3 handoff; latest uses the delivered review scripts')
    args = parser.parse_args()
    work = REPO / '.build' / ('headset_' + args.version + '_' + args.part)
    assert work.resolve().is_relative_to((REPO / '.build').resolve())
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    # Scripts are mirrored, but no NPZ, 3MF product, or other cached result is copied.
    for source in (HERE / 'history').rglob('*.py'):
        dest = work / source.relative_to(HERE / 'history')
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
    for directory in [FRONT, REAR]:
        for source in (REPO / directory).rglob('*.py'):
            dest = work / source.relative_to(REPO)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, dest)
    if args.version == 'requested':
        shutil.copy2(HERE / 'versions/compact_72/build_compact_front.py',
                     work / FRONT / 'geometry/build_compact_front.py')
        shutil.copy2(HERE / 'versions/rear_20/build_carbon_rear.py',
                     work / REAR / 'geometry/build_carbon_rear.py')
    (work / 'raw').mkdir(exist_ok=True)
    for source in (HERE / 'raw').iterdir():
        if source.is_file():
            shutil.copy2(source, work / 'raw' / source.name)
    def run(relative):
        print('Running ' + relative, flush=True)
        subprocess.run([sys.executable, str(work / relative)], cwd=work, check=True)
    def copy(source, dest):
        dest = work / dest
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(work / source, dest)
    stage = 'Headset_Prop_Stage1_2026-10-02'
    run(stage + '/inspect_reference.py')
    q = np.load(work / stage / 'reference_normal_mesh.npz')
    v = q['vertices'].copy() + [0,73.53516495,27.587837475]
    f = q['faces']
    original = 'Headset_FullCase_30mm_Preview_2026-10-02/preview_work/original_reference.npz'
    (work / original).parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(work / original, v=v, f=f)
    head = trimesh.load(work / 'raw/Medium_Symmetry.stl', process=True)
    native = work / 'Headset_Layout_v15/reference/Medium_Symmetry.npz'
    native.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(native, v=head.vertices, f=head.faces)
    registration = 'Headset_TwoParts_Preview_2026-10-02/headform'
    run(registration + '/register_head.py')
    for dest in ['Headset_FullCase_30mm_Preview_2026-10-02/headform', REAR + '/inputs']:
        copy(registration + '/Medium_Trial_Registered.npz', dest + '/Medium_Trial_Registered.npz')
    copy('raw/CS30_customer.stp', FRONT + '/inputs/CS30_customer.stp')
    run(FRONT + '/measure_camera_faces.py')
    run('Headset_Elastic25_2026-10-02/preview_work/prepare_head_display.py')
    copy('Headset_Elastic25_2026-10-02/preview_work/head_display.npz', REAR + '/inputs/head_display.npz')
    thin = 'Headset_ThinShell_Review_2026-10-02/geometry'
    copy(original, thin + '/original_reference.npz')
    run(thin + '/build_actual_face_limit.py')
    run(thin + '/build_thin_front.py')
    for name in ['original_reference','actual_original_forward_limit','wing_left','wing_right',
                 'front_tabs','window_cut','air_sealed_left','air_sealed_right']:
        copy(thin + '/' + name + '.npz', FRONT + '/inputs/' + name + '.npz')
    run(FRONT + '/geometry/build_compact_front.py')
    if args.part == 'rear':
        tray = 'Headset_Elastic25_2026-10-02/rear_work'
        run(tray + '/build_rear_tray.py')
        run(tray + '/assemble_rear_preview.py')
        for name in ['rear_tray','rear_inner_surface','rear_outer_surface','rear_fill']:
            copy(tray + '/' + name + '.npz', REAR + '/inputs/' + name + '.npz')
        run(REAR + '/geometry/build_carbon_rear.py')
    selected = FRONT if args.part == 'front' else REAR
    run(selected + '/export_review.py')
    report = json.loads((work / selected / 'model_verification.json').read_text())
    file = 'Front_Compact_Review_Wearing.3mf' if args.part == 'front' else 'Rear_Carbon6K_FlatBase_Review_Wearing.3mf'
    if args.version == 'latest':
        assembly = runpy.run_path(str(work / FRONT / 'export_assembly.py'))
        label = 'Front_Compact_Review' if args.part == 'front' else 'Rear_Carbon6K_top_open_flat_base'
        shell = 'front_unified_preview.npz' if args.part == 'front' else 'rear_unified_preview.npz'
        occupant = 'camera.npz' if args.part == 'front' else 'battery_preview.npz'
        assembly['export'](work / selected, file, work / selected / 'geometry' / shell,
                           work / selected / 'geometry' / occupant, label)
        report['reference_objects_included'] = ['head', 'camera' if args.part == 'front' else 'battery']
        report['file_sha256'] = hashlib.sha256((work / selected / file).read_bytes()).hexdigest()
    out = HERE / 'generated' / args.version
    out.mkdir(parents=True, exist_ok=True)
    shutil.copy2(work / selected / file, out / file)
    report['file'] = (out / file).relative_to(REPO).as_posix()
    report['source_mesh'] = Path(report['source_mesh']).relative_to(work).as_posix()
    report['extents_xyz_mm'] = (np.array(report['bounds_xyz_mm'][1])-report['bounds_xyz_mm'][0]).tolist()
    report['volume_cm3'] = report['volume_mm3']/1000
    report['raw_input_rebuild'] = True
    report['version'] = args.version
    (out / (args.part + '_verification.json')).write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps(report, indent=2))

if __name__ == '__main__':
    main()
