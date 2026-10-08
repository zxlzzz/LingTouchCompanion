"""Reproduce Hsinlung's printed front, with an explicit mesh-editing entry.

The retained 3MF is the authoritative geometry input; CAD history is absent.
Model coordinates use the source print axes with the bed centre removed.
They are not the former head/camera wearing coordinates. All units are mm.
"""
from pathlib import Path
import hashlib
import json
import manifold3d as md
import numpy as np
from source import P, SOURCE, read_source

G = P / 'geometry'
PRINT_ORIGIN = np.array([165., 160., 0.])


def modify_front(vertices, triangles):
    """Edit here for future changes to the actual printed front.

    Coordinates are mm: X lateral, Y along the print bed, Z up. Return
    vertex/triangle arrays; default returns the retained mesh unchanged.
    For solid additions/cuts, use manifold3d.Mesh64 and Manifold here and
    return to_mesh64().vert_properties[:, :3] and tri_verts of the result.
    No camera or registered head placement is inferred from this mesh.
    """
    return vertices, triangles


def checked_solid(v, f):
    assert v.ndim == 2 and v.shape[1] == 3 and np.isfinite(v).all()
    assert f.ndim == 2 and f.shape[1] == 3 and np.issubdtype(f.dtype, np.integer)
    assert f.min() >= 0 and f.max() < len(v)
    body = md.Manifold(md.Mesh64(
        vert_properties=np.ascontiguousarray(v, dtype=np.float64),
        tri_verts=np.ascontiguousarray(f, dtype=np.uint64)))
    assert body.status() == md.Error.NoError, body.status()
    assert body.volume() > 0 and len(body.decompose()) == 1
    return body


def main():
    G.mkdir(parents=True, exist_ok=True)
    (P / 'checks').mkdir(exist_ok=True)
    original_v, original_f, unused = read_source()
    model_v = original_v - PRINT_ORIGIN
    v, f = modify_front(model_v.copy(), original_f.copy())
    v, f = np.asarray(v, dtype=np.float64), np.asarray(f)
    solid = checked_solid(v, f)
    unchanged = np.array_equal(v, model_v) and np.array_equal(f, original_f)
    # Avoid subtraction/addition rounding for exact baseline reproduction.
    posed = original_v.copy() if unchanged else v + PRINT_ORIGIN
    np.savez_compressed(G / 'front_body.npz', v=v, f=f)
    np.savez_compressed(G / 'front_print.npz', v=posed, f=f)
    report = {
        'geometry_source': str(SOURCE.relative_to(P.parent.parent)).replace('\\', '/'),
        'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        'build_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        'unmodified_final_baseline': unchanged,
        'coordinate_system': 'Source print axes, bed centre removed; not wearing coordinates.',
        'model_to_print_rotation': np.eye(3).tolist(),
        'model_to_print_translation_mm': PRINT_ORIGIN.tolist(),
        'vertices': len(v), 'triangles': len(f), 'components': len(solid.decompose()),
        'volume_cm3': float(solid.volume()) / 1000,
        'print_bounds_xyz_mm': [posed.min(0).tolist(), posed.max(0).tolist()],
        'limitations': 'Finished mesh baseline, not recovered parametric CAD history. Old camera/head fit reports do not apply.'}
    (G / 'geometry_values.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
