"""Fill the old rear connector windows without rewriting any previous deliverable."""
from pathlib import Path
import hashlib
import json
import numpy as np
import manifold3d as md

P = Path(__file__).resolve().parent
BASE = P.parent
ROOT = BASE.parent
G = P / 'geometry'
C = P / 'checks'
M = md.Manifold

def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def load(path):
    q = np.load(path)
    m = M(md.Mesh64(vert_properties=np.ascontiguousarray(q['v'], dtype=np.float64),
                   tri_verts=np.ascontiguousarray(q['f'], dtype=np.uint64)))
    assert m.status() == md.Error.NoError, (path, m.status())
    return m

def box(lo, hi):
    lo, hi = np.array(lo, float), np.array(hi, float)
    return M.cube(tuple(hi-lo)).translate(tuple(lo))

def save(path, body):
    mesh = body.to_mesh64()
    v = np.asarray(mesh.vert_properties)[:, :3]
    f = np.asarray(mesh.tri_verts)
    np.savez_compressed(path, v=v, f=f)
    return v, f

def main():
    G.mkdir(parents=True, exist_ok=True)
    C.mkdir(parents=True, exist_ok=True)
    originals = sorted(ROOT.glob('Headset_*/*.3mf'))
    original_hashes = {str(p.relative_to(ROOT)).replace('\\', '/'): digest(p) for p in originals}
    old = load(BASE/'geometry/rear_body.npz')
    original_bounds = np.array(old.bounding_box()).reshape(2, 3)
    source_fill = load(BASE/'inputs/rear_fill.npz')
    # This source follows the original rear tray's outside anatomical surface.
    # Using it avoids filling inward through the existing head-contact face.
    connector = source_fill ^ box([-20, 100, 25.5], [20, 203.4, 52.9])
    connector += box([-20, 203.1, 25.5], [20, 204.8, 52.9])
    # Recover only the material of the original outer rounded battery envelope.
    # Intersecting rather than adding a raw rectangular patch preserves its skin.
    from importlib.util import spec_from_file_location, module_from_spec
    spec = spec_from_file_location('unchanged_rear_source', BASE/'build.py')
    base = module_from_spec(spec)
    spec.loader.exec_module(base)
    outer_case = base.x_prism(base.round_rect(27.4, 27.4, 3), 95, -47.5, 217, 39.2)
    port_patch = outer_case ^ box([45.5, 211, 36.2], [48, 223, 42.2])
    revised = old + connector + port_patch
    assert revised.status() == md.Error.NoError and len(revised.decompose()) == 1
    v, f = save(G/'rear_body.npz', revised)
    edges = np.sort(np.concatenate([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]]), axis=1)
    _, edge_counts = np.unique(edges, axis=0, return_counts=True)
    assert (edge_counts == 2).all(), 'Nonmanifold revised rear'
    bounds = np.array([v.min(0), v.max(0)])
    assert np.allclose(bounds, original_bounds, atol=1e-7), (bounds, original_bounds)
    # No new plastic enters the battery space, spring release slits or strap slots.
    added = revised-old
    unchanged_regions = {
        'battery_loading_mouth': box([-45.5, 205.3, 39.2], [45.5, 228.7, 80]),
        'battery_body': load(BASE/'geometry/battery.npz'),
        'left_strap_slot': box([-47.5, 198.3, 28.5], [-42.5, 201.3, 54.5]),
        'right_strap_slot': box([42.5, 198.3, 28.5], [47.5, 201.3, 54.5]),
        'spring_working_wall': box([-43.6, 228.6, 33.65], [43.6, 230.8, 46.25]),
    }
    intrusion = {name: max(0.0, float((added ^ region).volume())) for name, region in unchanged_regions.items()}
    assert max(intrusion.values()) < 1e-7, intrusion
    expected_fill = connector-old
    assert float((expected_fill-revised).volume()) < 1e-7
    assert float((old-revised).volume()) < 1e-7, 'Revision removed original plastic'
    # Compare first surfaces seen from the head across the whole contact patch.
    # This detects fill incorrectly placed inward through the anatomical face.
    import bpy
    from mathutils.bvhtree import BVHTree
    from mathutils import Vector
    original = np.load(BASE/'geometry/rear_body.npz')
    trees = [BVHTree.FromPolygons(vertices.tolist(), faces.tolist(), all_triangles=True)
             for vertices, faces in [(original['v'], original['f']), (v, f)]]
    contact_pairs = [[tree.ray_cast(Vector((float(x),100.,float(z))), Vector((0.,1.,0.)))[0]
                      for tree in trees]
                     for x in np.linspace(-19.5,19.5,40) for z in np.linspace(25.7,52.7,28)]
    assert all(a is not None and b is not None for a,b in contact_pairs)
    contact_error = max((a-b).length for a,b in contact_pairs)
    assert contact_error < 1e-6, contact_error
    minimum_rear_fill_y = float(np.min(np.array(connector.to_mesh64().vert_properties)[:,1]))
    results = {
        'rear_redesigned': True,
        'decisions': {
            'connector_windows': 'Filled across the entire existing 40 mm anatomical tray width and 27.4 mm height.',
            'nominal_unmeasured_usb_hole': 'Closed using the original rounded battery envelope.',
            'preserved': 'Genuine curved head-contact tray, outer envelope, battery mouth and cavity, spring release cuts, all strap slot coordinates.',
            'previous_files': 'No previously finished 3MF or base script is overwritten.',
        },
        'old_volume_cm3': float(old.volume())/1000,
        'new_volume_cm3': float(revised.volume())/1000,
        'added_plastic_cm3': float(added.volume())/1000,
        'connector_added_plastic_cm3': float((connector-old).volume())/1000,
        'usb_patch_added_plastic_cm3': float((port_patch-old).volume())/1000,
        'bounds_xyz_mm': bounds.tolist(),
        'dimensions_xyz_mm': (bounds[1]-bounds[0]).tolist(),
        'connector_x_mm': [-20,20], 'connector_z_mm': [25.5,52.9],
        'connector_minimum_y_mm': minimum_rear_fill_y,
        'closed_connected_manifold': True, 'components': len(revised.decompose()),
        'vertices': len(v), 'triangles': len(f),
        'added_material_in_preserved_regions_mm3': intrusion,
        'head_contact_surface_check': {'first_head_side_hits':len(contact_pairs), 'maximum_old_new_difference_mm':contact_error},
        'previous_deliverable_sha256': original_hashes,
        'sources': ['Headset_Rear/geometry/rear_body.npz','Headset_Rear/inputs/rear_fill.npz','Headset_Rear/build.py'],
        'physical_fit_unverified': True,
    }
    assert all(digest(ROOT/p) == sha for p,sha in original_hashes.items())
    (G/'geometry_values.json').write_text(json.dumps(results, indent=2), encoding='utf8')
    (C/'build.json').write_text(json.dumps(results, indent=2), encoding='utf8')
    print(json.dumps({k:results[k] for k in ['old_volume_cm3','new_volume_cm3','added_plastic_cm3','dimensions_xyz_mm','closed_connected_manifold']}, indent=2))

if __name__ == '__main__':
    main()
