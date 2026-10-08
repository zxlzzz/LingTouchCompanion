"""Check finished-front reproduction and topology, not historical fit.

Baseline comparison is always reported. Deliberate later edits are validated
against the generated mesh; use --require-baseline to require exact identity.
"""
import argparse
import hashlib
import json
import numpy as np
from build import checked_solid, PRINT_ORIGIN
from source import P, SOURCE, read_source, SETTINGS_ENTRY


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--require-baseline', action='store_true')
    args = ap.parse_args()
    original_v, original_f, source_members = read_source()
    path = P / 'Front_CS30_Mount_Print.3mf'
    v, f, members = read_source(path, check_digest=False)
    body = checked_solid(v, f)
    with np.load(P / 'geometry/front_body.npz') as data:
        model_v, model_f = data['v'], data['f']
    with np.load(P / 'geometry/front_print.npz') as data:
        posed_v, posed_f = data['v'], data['f']
    edges = np.sort(np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]]), axis=1)
    unused, incidence = np.unique(edges, axis=0, return_counts=True)
    report = {
        'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        'output_sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
        'whole_archive_identical': SOURCE.read_bytes() == path.read_bytes(),
        'vertices_identical': np.array_equal(v, original_v),
        'triangles_identical': np.array_equal(f, original_f),
        'maximum_vertex_difference_mm': float(np.abs(v-original_v).max()) if v.shape == original_v.shape else None,
        'export_matches_generated_mesh': np.array_equal(v, posed_v) and np.array_equal(f, posed_f),
        'model_to_print_pose_error_mm': float(np.abs(v-(model_v+PRINT_ORIGIN)).max()) if v.shape == model_v.shape else None,
        'model_to_print_topology_preserved': np.array_equal(f, model_f),
        'saved_settings_bytes_identical': members[SETTINGS_ENTRY] == source_members[SETTINGS_ENTRY],
        'closed_connected_manifold': bool((incidence == 2).all() and len(body.decompose()) == 1),
        'vertices': len(v), 'triangles': len(f),
        'print_dimensions_xyz_mm': (v.max(0)-v.min(0)).tolist(),
        'volume_cm3': float(body.volume())/1000,
        'scope': 'Reproduction of the printed front; old camera/head fit and retention reports do not apply.'}
    report['baseline_reproduction_pass'] = bool(report['whole_archive_identical'] and report['vertices_identical']
                                                and report['triangles_identical'])
    report['pass'] = bool(report['export_matches_generated_mesh'] and report['model_to_print_topology_preserved']
                          and report['model_to_print_pose_error_mm'] is not None
                          and report['model_to_print_pose_error_mm'] < 1e-9
                          and report['saved_settings_bytes_identical'] and report['closed_connected_manifold']
                          and (not args.require_baseline or report['baseline_reproduction_pass']))
    (P / 'checks/reproduction.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps(report, indent=2), flush=True)
    assert report['pass'], 'Verification failed; inspect checks/reproduction.json'


if __name__ == '__main__':
    main()
