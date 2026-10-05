"""Audit the simple added camera slot against the actual camera and head.

The previously accepted structural front is the unchanged baseline. Only a
low tray, two side guides, a front stop and two small rear lips are permitted.
The slot has an intentional lift-and-slide removal path; it is not a latch.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import time

import manifold3d as md
import numpy as np

P = Path(__file__).resolve().parent
BASE = P.parent
ROOT = BASE.parent
G = P / 'geometry'
C = P / 'checks'
SOURCE = BASE / 'structural' / 'geometry'
TOL = .001
M = md.Manifold


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def load(path):
    with np.load(path) as q:
        return {key: q[key] for key in q.files}


def solid(q):
    result = M(md.Mesh64(vert_properties=np.ascontiguousarray(q['v'], dtype=np.float64),
                         tri_verts=np.ascontiguousarray(q['f'], dtype=np.uint64)))
    assert result.status() == md.Error.NoError, result.status()
    return result


def box(lo, hi):
    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    return M.cube(tuple(hi-lo)).translate(tuple(lo))


def volume(body):
    return max(0., float(body.volume()))


def expected_slot(camera):
    refs = camera['v'][np.unique(camera['f'])]
    low, high = refs.min(0), refs.max(0)
    base_z = float(low[2])-1e-5
    inner_l, inner_r = low[0]-.3, high[0]+.3
    inner_front = low[1]-.3
    outer_l, outer_r, outer_front = inner_l-1.6, inner_r+1.6, inner_front-1.6
    envelopes = [box([outer_l, outer_front, 23.3], [outer_r, 3.8, base_z]),
                 box([outer_l, outer_front, 23.3], [inner_l, 3.8, 38.5]),
                 box([inner_r, outer_front, 23.3], [outer_r, 3.8, 38.5]),
                 box([inner_l, outer_front, 23.3], [inner_r, inner_front, base_z+3])]
    lips = []
    for x0, x1 in [(-32., -15.), (15., 32.)]:
        envelopes.append(box([x0, 3.6, 23.3], [x1, 6.5, base_z]))
        lip = box([x0, 4.9, base_z], [x1, 6.5, base_z+.8])
        lips.append(lip)
        envelopes.append(lip)
    return {'camera_bounds_xyz_mm': [low.tolist(), high.tolist()],
            'inner_x_mm': [inner_l, inner_r], 'inner_front_y_mm': inner_front,
            'nominal_side_clearance_mm': .3, 'nominal_front_clearance_mm': .3,
            'floor_z_mm': base_z, 'side_wall_top_z_mm': 38.5,
            'front_stop_top_z_mm': base_z+3, 'rear_lip_top_z_mm': base_z+.8,
            'rear_lip_x_ranges_mm': [[-32, -15], [15, 32]], 'rear_lip_y_mm': [4.9, 6.5]}, M.batch_boolean(envelopes, md.OpType.Add), M.batch_boolean(lips, md.OpType.Add)


def first_axis_contact(camera_hull, body, direction, maximum=5):
    axis = np.asarray(direction, float)
    if volume(camera_hull.translate(tuple(axis*maximum)) ^ body) <= 1e-6:
        return None
    lo, hi = 0., maximum
    for unused in range(25):
        mid = (lo+hi)/2
        if volume(camera_hull.translate(tuple(axis*mid)) ^ body) > 1e-6:
            hi = mid
        else:
            lo = mid
    return [lo, hi]


def physical_lip_contact(camera, lips):
    import vtk
    from vtk.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray
    def poly(vertices, faces):
        points = vtk.vtkPoints()
        points.SetData(numpy_to_vtk(np.ascontiguousarray(vertices, dtype=np.float64), deep=True))
        cells = vtk.vtkCellArray()
        cells.SetData(numpy_to_vtkIdTypeArray(np.arange(0, len(faces)*3+1, 3, dtype=np.int64), deep=True),
                      numpy_to_vtkIdTypeArray(np.ascontiguousarray(faces.ravel(), dtype=np.int64), deep=True))
        result = vtk.vtkPolyData()
        result.SetPoints(points)
        result.SetPolys(cells)
        return result
    mesh = lips.to_mesh64()
    collision = vtk.vtkCollisionDetectionFilter()
    collision.SetInputData(0, poly(camera['v'], camera['f']))
    collision.SetInputData(1, poly(np.asarray(mesh.vert_properties)[:, :3], np.asarray(mesh.tri_verts)))
    moving, fixed = vtk.vtkMatrix4x4(), vtk.vtkMatrix4x4()
    moving.Identity()
    fixed.Identity()
    collision.SetMatrix(0, moving)
    collision.SetMatrix(1, fixed)
    collision.SetCollisionModeToFirstContact()
    collision.SetBoxTolerance(0)
    collision.SetCellTolerance(0)
    rows = []
    for dy in [0., .1, .2, .3, .4, 1.]:
        moving.SetElement(1, 3, dy)
        collision.Update()
        rows.append({'rearward_shift_mm': dy, 'actual_camera_surface_hits_lip': bool(collision.GetNumberOfContacts())})
    return {'method': 'Actual STEP triangles against the retained lip triangles; the convex hull is not the blocking witness.',
            'samples': rows,
            'pass': all(not row['actual_camera_surface_hits_lip'] for row in rows[:3])
                    and all(row['actual_camera_surface_hits_lip'] for row in rows[3:])}


def main():
    start = time.time()
    C.mkdir(exist_ok=True)
    helper_path = BASE / 'structural' / 'verify.py'
    helper = module(helper_path, 'established_geometry_audit_methods')
    helper.P, helper.G, helper.C, helper.SOURCE = P, G, C, SOURCE
    paths = [Path(__file__), P / 'build.py', helper_path, BASE / 'build.py',
             BASE / 'checks' / 'head_fit.py', BASE / 'checks' / 'mesh_distance.py',
             ROOT / 'Headset_Inputs' / 'datums.json', ROOT / 'Headset_Inputs' / 'Medium_Trial_Registered.npz']
    for folder in [G, SOURCE]:
        paths.extend([folder / (name+'.npz') for name in ['front_body', 'camera', 'camera_optics', 'nose_support']])
        paths.append(folder / 'geometry_values.json')
    hashes = {str(path.relative_to(ROOT)).replace('\\', '/'): digest(path) for path in paths}
    q = load(G / 'front_body.npz')
    body = solid(q)
    previous = solid(load(SOURCE / 'front_body.npz'))
    camera = load(G / 'camera.npz')
    values = json.loads((G / 'geometry_values.json').read_text('utf8'))
    previous_values = json.loads((SOURCE / 'geometry_values.json').read_text('utf8'))
    params, allowed, lips = expected_slot(camera)
    added, lost = body-previous, previous-body
    construction = module(BASE / 'build.py', 'unchanged_external_envelope')
    outer = construction.loft([construction.profile(x) for x in np.linspace(-66, 66, 281)]) ^ construction.below_print_plane()
    external_addition = volume(added-outer)
    identity = {name: helper.identity(name) for name in ['camera', 'camera_optics', 'nose_support']}
    refs = camera['v'][np.unique(camera['f'])]
    hull = M.hull_points(np.unique(np.round(refs, 8), axis=0))
    installed_overlap = volume(hull ^ body)
    lift = 1.2
    raised = hull.translate((0, 0, lift))
    vertical_sweep = M.batch_hull([hull, raised])
    rear_sweep = M.batch_hull([raised, raised.translate((0, 80, 0))])
    vertical_overlap, rear_overlap = volume(vertical_sweep ^ body), volume(rear_sweep ^ body)
    contact = {name: first_axis_contact(hull, body, direction) for name, direction in
               [('left', (-1, 0, 0)), ('right', (1, 0, 0)), ('forward', (0, -1, 0)), ('rearward', (0, 1, 0))]}
    edges = np.sort(np.concatenate([q['f'][:, [0, 1]], q['f'][:, [1, 2]], q['f'][:, [2, 0]]]), axis=1)
    _, incidence = np.unique(edges, axis=0, return_counts=True)
    topology_ok = bool(len(body.decompose()) == 1 and (incidence == 2).all())
    facet, unused = helper.print_facet(body, values)
    lip_missing = volume(lips-body)
    optics = helper.optical_checks(body, camera, values)
    physical = physical_lip_contact(camera, lips)
    report = {'source_sha256': hashes, 'topology': {'closed_connected_manifold': topology_ok,
              'components': len(body.decompose()), 'volume_cm3': volume(body)/1000},
              'change_scope': {'baseline': str((SOURCE / 'front_body.npz').relative_to(ROOT)),
                               'previous_material_removed_mm3': volume(lost),
                               'material_added_mm3': volume(added),
                               'added_material_outside_permitted_slot_envelopes_mm3': volume(added-allowed),
                               'added_material_outside_original_external_shell_envelope_mm3': external_addition,
                               'pass': volume(lost) <= TOL and volume(added-allowed) <= TOL and external_addition <= TOL},
              'unchanged_reference_arrays': identity, 'slot_dimensions': params,
              'installed_camera': {'conservative_hull_overlap_mm3': installed_overlap, 'pass': installed_overlap <= TOL},
              'slot_horizontal_play': {'first_contact_bounds_mm': contact,
                                       'method': 'Actual final material versus translated conservative camera hull; volume threshold 0.000001 mm3.',
                                       'pass': all(bounds is not None and .15 <= bounds[0] <= .4 for bounds in contact.values())},
              'rear_lips': {'specified_lip_material_missing_mm3': lip_missing,
                            'actual_camera_surface_contact': physical, 'pass': lip_missing <= TOL and physical['pass']},
              'installation_removal_path': {'lift_mm': lift, 'rearward_travel_mm': 80,
                                            'vertical_swept_hull_overlap_mm3': vertical_overlap,
                                            'raised_rearward_swept_hull_overlap_mm3': rear_overlap,
                                            'installation': 'Off the head, hold the camera 1.2 mm above its final position, slide forward through the rear opening, then lower it into the slot.',
                                            'removal': 'Lift the camera 1.2 mm, then slide it rearward out of the open front assembly.',
                                            'pass': vertical_overlap <= TOL and rear_overlap <= TOL},
              'optics': optics, 'print_facet': facet,
              'print_facet_metadata_unchanged': values['print_foot'] == previous_values['print_foot'],
              'retention_limit': 'The tray and lips locate the camera and block direct horizontal sliding. The deliberate lift-and-slide path permits removal; this is not a positive latch, and no drop, inversion, friction or real-print strength test is claimed.',
              'limitations': ['The geometric fit is based on the actual unchanged supplied camera and registered head meshes.',
                              'Printing tolerance, wear, comfort and real assembly tightness require a physical sample.',
                              'Optical openings and forward lens exposure are checked; operational camera field of view is not certified.']}
    print(json.dumps({key: report[key] for key in ['change_scope', 'installed_camera', 'slot_horizontal_play', 'rear_lips', 'installation_removal_path']}, indent=2), flush=True)
    head = helper.head_and_slots()
    report['head_fit'] = {key: head[key] for key in ['head_sha256', 'parts', 'camera_first_skin_contact',
                                                  'classification_contact_epsilon_mm', 'classification_limit',
                                                  'all_parts_sampled_penetration_within_contact_epsilon']}
    report['terminal_slots'] = head['terminal_slots']
    unchanged = all(digest(ROOT/path) == expected for path, expected in hashes.items())
    report['sources_unchanged_during_verification'] = unchanged
    report['runtime_seconds'] = time.time()-start
    report['pass'] = bool(topology_ok and report['change_scope']['pass'] and all(item['all_arrays_identical'] for item in identity.values())
                          and report['installed_camera']['pass'] and report['slot_horizontal_play']['pass']
                          and report['rear_lips']['pass'] and report['installation_removal_path']['pass']
                          and optics['pass'] and facet['pass'] and report['print_facet_metadata_unchanged']
                          and head['all_parts_sampled_penetration_within_contact_epsilon']
                          and head['terminal_slots']['all_slot_locations_and_reach_preserved'] and unchanged)
    (C / 'fit.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps({'pass': report['pass'], 'runtime_seconds': report['runtime_seconds'],
                      'source_unchanged': unchanged, 'retention_limit': report['retention_limit']}, indent=2), flush=True)
    assert report['pass'], 'Camera slot verification failed; inspect checks/fit.json'


if __name__ == '__main__':
    main()
