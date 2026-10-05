"""Independent checks of the one-piece structural simplification.

The actual camera, registered head, nose and terminal datums are inputs.
Camera retention is explicitly unverified after removal of its strap eyes.
Only checks/fit.json is written; earlier geometry and reports remain inputs.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import math
import sys
import tempfile
import time

import manifold3d as md
import numpy as np

P = Path(__file__).resolve().parent
BASE = P.parent
ROOT = BASE.parent
G = P / 'geometry'
C = P / 'checks'
SOURCE = BASE / 'revised' / 'geometry'
M = md.Manifold
TOL_VOLUME = .001


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load(path):
    with np.load(path) as data:
        return {key: data[key] for key in data.files}


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def solid(q):
    body = M(md.Mesh64(vert_properties=np.ascontiguousarray(q['v'], dtype=np.float64),
                       tri_verts=np.ascontiguousarray(q['f'], dtype=np.uint64)))
    assert body.status() == md.Error.NoError, body.status()
    return body


def box(lo, hi):
    lo, hi = np.asarray(lo, float), np.asarray(hi, float)
    return M.cube(tuple(hi - lo)).translate(tuple(lo))


def volume(body):
    return max(0., float(body.volume()))


def describe(body):
    return [{'volume_mm3': volume(part), 'bounds_xyz_mm': list(part.bounding_box())}
            for part in body.decompose() if volume(part) > 1e-8]


def identity(name):
    old = load(SOURCE / (name + '.npz'))
    new = load(G / (name + '.npz'))
    equal = set(old) == set(new) and all(np.array_equal(old[key], new[key]) for key in old)
    return {'all_arrays_identical': equal,
            'source_sha256': digest(SOURCE / (name + '.npz')),
            'current_sha256': digest(G / (name + '.npz'))}


def rounded(width, height, radius, center):
    points = []
    for x, z, angle in [(width/2-radius, height/2-radius, 0),
                        (-width/2+radius, height/2-radius, 90),
                        (-width/2+radius, -height/2+radius, 180),
                        (width/2-radius, -height/2+radius, 270)]:
        for t in np.linspace(math.radians(angle), math.radians(angle+90), 25):
            points.append([center[0]+x+radius*math.cos(t), center[1]+z+radius*math.sin(t)])
    return md.CrossSection([np.asarray(points)])


def optical_checks(body, camera, values):
    old_values = json.loads((SOURCE / 'geometry_values.json').read_text('utf8'))
    native = load(BASE / 'inputs' / 'camera_physical_native.npz')
    transform = np.asarray(values['camera_transform_native_to_wearing'], float)
    residual = float(np.abs(native['v'] @ transform[:, :3].T + transform[:, 3] - camera['v']).max())
    actual = []
    bores = []
    for item in values['optics']:
        width, height = item['opening_mm']
        # A 0.002 mm inset avoids classifying shared boundary facets as a plug.
        if item['name'] == 'TX':
            cs = rounded(width, height, 1, (item['x'], item['z'])).offset(-.002)
            bore = cs.extrude(60).transform([[1, 0, 0, 0], [0, 0, -1, 20], [0, 1, 0, 0]])
        else:
            bore = M.cylinder(60, width/2-.002, width/2-.002, 96).transform(
                [[1, 0, 0, item['x']], [0, 0, -1, 20], [0, 1, 0, item['z']]])
        blocked = volume(body ^ bore)
        bores.append({'name': item['name'], 'specified_opening_mm': item['opening_mm'],
                      'continuous_y_range_mm': [-40, 20], 'boundary_inset_mm': .002,
                      'plastic_within_bore_mm3': blocked, 'pass': blocked <= TOL_VOLUME})
    for ident, name in [(0, 'RGB'), (1, 'RX'), (2, 'TX')]:
        refs = np.unique(camera['f'][camera['part'] == ident])
        points = native['v'][refs]
        keep = np.abs(points[:, 2]+1) < 1e-6
        if name == 'TX':
            keep &= (points[:, 0] >= 3.5-1e-6) & (points[:, 0] <= 10.5+1e-6) & (np.abs(points[:, 1]) <= 2.25+1e-6)
        fronts = camera['v'][refs[keep]]
        blocked = [point.tolist() for point in fronts
                   if body.ray_cast(tuple(point), tuple(point + [0, -100, 0]))]
        actual.append({'name': name, 'actual_lens_front_vertices': len(fronts),
                       'blocked_front_vertices': len(blocked), 'blocked_examples_mm': blocked[:5],
                       'pass': len(fronts) > 0 and not blocked})
    return {'declared_optics_unchanged': values['optics'] == old_values['optics'],
            'camera_transform_unchanged': values['camera_transform_native_to_wearing'] == old_values['camera_transform_native_to_wearing'],
            'native_camera_transform_max_residual_mm': residual,
            'continuous_bores': bores, 'actual_lens_forward_rays': actual,
            'pass': values['optics'] == old_values['optics'] and residual < 1e-8
                    and all(item['pass'] for item in bores + actual)}


def removed_features(body, original):
    probes = []
    for side in [-1, 1]:
        ranges = [('internal_plate_and_eye', [45.5, -.8, 28], [53.4, 5, 55]),
                  ('temple_upper_structure', [80, 60, 50], [99, 125, 70])]
        for name, low, high in ranges:
            if side < 0:
                low, high = [-high[0], low[1], low[2]], [-low[0], high[1], high[2]]
            probe = box(low, high)
            old_volume, new_volume = volume(original ^ probe), volume(body ^ probe)
            probes.append({'feature': name, 'side': side, 'probe_bounds_xyz_mm': [low, high],
                           'previous_material_mm3': old_volume, 'remaining_material_mm3': new_volume,
                           'pass': old_volume > 1 and new_volume <= TOL_VOLUME})
    transverse = body.transform([[1, 0, 0, 0], [0, 0, 1, 0], [0, 1, 0, 0]])
    sections = []
    for y in [60, 100, 125]:
        polygons = transverse.slice(y).to_polygons()
        relevant = [np.asarray(poly) for poly in polygons if np.abs(np.asarray(poly)[:, 0].mean()) > 70]
        bounds = [[poly.min(0).tolist(), poly.max(0).tolist()] for poly in relevant]
        # The terminal upper edge grows over Y110..150 with 6 mm easing
        # at either end. At Y125 this lies in the constant-slope segment.
        expected_top = 47. if y <= 110 else 47.+8.2*(y-110.-3.)/34.
        valid = len(relevant) == 2 and all(abs(np.ptp(poly[:, 0])-3.4) < .01 and
                                         abs(poly[:, 1].min()-35) < .01 and
                                         abs(poly[:, 1].max()-expected_top) < .01 for poly in relevant)
        sections.append({'wearing_y_mm': y, 'compact_arm_contours': len(relevant),
                         'expected_upper_edge_z_mm': expected_top,
                         'xz_bounds_mm': bounds, 'pass': valid})
    return {'probes': probes, 'temple_sections': sections,
            'pass': all(item['pass'] for item in probes + sections)}


def shoulder_sections(body):
    records = []
    for side in [-1, 1]:
        for t in np.linspace(.005, 1, 41):
            angle = t*np.pi/2
            theta = np.arctan2(56.25*np.sin(angle), 22.9*np.cos(angle))
            x = side*(65.5+22.9*np.sin(angle))
            y = -13.25+56.25*(1-np.cos(angle))
            nx, ny = -side*np.sin(theta), np.cos(theta)
            tx, ty = side*np.cos(theta), np.sin(theta)
            section = body.transform([[nx, ny, 0, -nx*x-ny*y], [0, 0, 1, 0],
                                      [tx, ty, 0, -tx*x-ty*y]]).slice(0)
            local = section ^ md.CrossSection.square((12, 80)).translate((-6, 0))
            areas = sorted([float(part.area()) for part in local.decompose()], reverse=True)
            records.append({'side': side, 'fraction_along_curved_strip': float(t),
                            'main_section_area_mm2': areas[0] if areas else 0.,
                            'other_nearby_shell_section_areas_mm2': areas[1:]})
    minimum = min(records, key=lambda row: row['main_section_area_mm2'])
    return {'sampled_planes_per_side': 41, 'minimum_main_section_area_mm2': minimum['main_section_area_mm2'],
            'minimum_witness': minimum,
            'method': 'Material slices perpendicular to the curved strip, restricted to a 12 mm lateral window. The largest section is the strip; separate small roof/floor sections may also cross the window near the root.',
            'limitation': 'Sampled cross-sectional area rules out an observed narrow neck; it is not a strength certification.',
            'pass': minimum['main_section_area_mm2'] > 30}


def print_facet(body, values):
    declared = values.get('print_foot')
    if not declared:
        return None, None
    angle = float(declared['rotation_about_wearing_x_deg'])
    bottom = float(declared['untrimmed_print_z_min'])
    depth = float(declared['trim_depth_mm'])
    cut_height = bottom+depth
    rotated = body.rotate((angle, 0, 0))
    mesh = rotated.to_mesh64()
    vertices = np.asarray(mesh.vert_properties)[:, :3]
    triangles = vertices[np.asarray(mesh.tri_verts)]
    cross = np.cross(triangles[:, 1]-triangles[:, 0], triangles[:, 2]-triangles[:, 0])
    area = np.linalg.norm(cross, axis=1)/2
    selected = (np.max(np.abs(triangles[:, :, 2]-cut_height), axis=1) < 1e-6) & (cross[:, 2] < -1e-10)
    centers = triangles[selected].mean(1)
    measurements = []
    missing = []
    for center in centers:
        origin = center+np.array([0, 0, 1e-5])
        hits = rotated.ray_cast(tuple(origin), tuple(origin+np.array([0, 0, 80.])))
        if hits:
            measurements.append(float(hits[0].position[2]-center[2]))
        else:
            missing.append(center.tolist())
    actual_area = float(area[selected].sum())
    removed_region = box([-500, -500, -500], [500, 500, cut_height+1e-8]).rotate((-angle, 0, 0))
    minimum = min(measurements) if measurements else 0.
    report = {'rotation_about_wearing_x_deg': angle, 'trim_depth_mm': depth,
              'untranslated_print_plane_z_mm': cut_height,
              'declared_flat_area_mm2': declared['flat_area_mm2'], 'actual_flat_area_mm2': actual_area,
              'flat_area_error_mm2': abs(actual_area-float(declared['flat_area_mm2'])),
              'cut_face_centroids_checked': len(centers), 'unresolved_thickness_rays': len(missing),
              'minimum_sampled_remaining_wall_mm': minimum,
              'maximum_sampled_remaining_wall_mm': max(measurements) if measurements else 0.,
              'method': 'Every new bed-facing planar facet centroid is ray-cast along the inward print normal to the first material exit. A 0.00001 mm inset avoids self-intersection; the original face position remains the thickness origin.',
              'limitation': 'These are actual mesh thickness samples across the facet, not an exact continuous minimum or a strength certification.',
              'pass': bool(len(centers) and not missing and minimum > .8 and actual_area > 150
                           and abs(actual_area-float(declared['flat_area_mm2'])) < .01)}
    return report, removed_region


def head_and_slots():
    sys.path.insert(0, str(BASE / 'checks'))
    audit = module(BASE / 'checks' / 'head_fit.py', 'current_head_and_slot_audit')
    audit.ART = P
    audit.G = G
    previous_path = C / 'fit.json'
    if previous_path.exists():
        previous = json.loads(previous_path.read_text('utf8'))
        dependencies = [G / 'front_body.npz', G / 'camera.npz', G / 'geometry_values.json',
                        ROOT / 'Headset_Inputs' / 'datums.json', ROOT / 'Headset_Inputs' / 'Medium_Trial_Registered.npz',
                        BASE / 'checks' / 'head_fit.py', BASE / 'checks' / 'mesh_distance.py']
        hashes = previous.get('source_sha256', {})
        if ('head_fit' in previous and 'terminal_slots' in previous and
                all(hashes.get(str(path.relative_to(ROOT)).replace('\\', '/')) == digest(path) for path in dependencies)):
            reused = dict(previous['head_fit'])
            reused['terminal_slots'] = previous['terminal_slots']
            reused['reused_for_identical_geometry_head_datums_and_audit_methods'] = True
            return reused
    with tempfile.TemporaryDirectory(prefix='structural_fit_') as temporary:
        audit.OUTPUT = Path(temporary) / 'head_fit.json'
        # Only the earlier camera/head collision datum may be reused, and
        # audit.distances checks both hashes before doing so.
        # The audit computes current camera/head evidence when no cache exists.
        audit.distances()
        audit.classify(.05)
        audit.slots()
        return json.loads(audit.OUTPUT.read_text('utf8'))


def main():
    start = time.time()
    C.mkdir(exist_ok=True)
    source_files = [P / 'build.py', Path(__file__), G / 'geometry_values.json',
                    BASE / 'checks' / 'head_fit.py', BASE / 'checks' / 'mesh_distance.py',
                    ROOT / 'Headset_Inputs' / 'datums.json', ROOT / 'Headset_Inputs' / 'Medium_Trial_Registered.npz']
    for name in ['front_body', 'nose_support', 'camera', 'camera_optics']:
        source_files += [G / (name+'.npz'), SOURCE / (name+'.npz')]
    hashes = {str(path.relative_to(ROOT)).replace('\\', '/'): digest(path) for path in source_files}
    values = json.loads((G / 'geometry_values.json').read_text('utf8'))
    assert values['head_audit_parts'] == ['front_body', 'camera'], 'Stale or incomplete audited-part manifest'
    q, camera = load(G / 'front_body.npz'), load(G / 'camera.npz')
    body = solid(q)
    original = solid(load(SOURCE / 'front_body.npz'))
    nose = solid(load(G / 'nose_support.npz'))
    refs = camera['v'][np.unique(camera['f'])]
    hull = M.hull_points(np.unique(np.round(refs, 8), axis=0))
    overlap = hull ^ body
    rearward_sweep = M.batch_hull([hull, hull.translate((0, 80, 0))]) ^ body
    faces = q['f']
    edges = np.sort(np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]]), axis=1)
    _, counts = np.unique(edges, axis=0, return_counts=True)
    topology_ok = bool((counts == 2).all() and len(body.decompose()) == 1 and body.volume() > 0)
    identities = {name: identity(name) for name in ['nose_support', 'camera', 'camera_optics']}
    nose_missing = volume(nose-body)
    # This mask isolates the central roof from the deliberately removed
    # plates, stops and shoulder structures.
    roof_mask = box([-45, -100, 57.1], [45, 50, 100])
    old_roof, new_roof = original ^ roof_mask, body ^ roof_mask
    facet_report, facet_region = print_facet(body, values)
    roof_removed, roof_added = old_roof-new_roof, new_roof-old_roof
    declared_roof_removal = volume(roof_removed ^ facet_region) if facet_region is not None else 0.
    unexpected_roof_removal = volume(roof_removed-facet_region) if facet_region is not None else volume(roof_removed)
    roof_difference = unexpected_roof_removal + volume(roof_added)
    report = {'source_sha256': hashes,
              'topology': {'closed_connected_manifold': topology_ok, 'components': len(body.decompose()),
                           'all_edge_incidence_two': bool((counts == 2).all()),
                           'volume_cm3': volume(body)/1000, 'previous_volume_cm3': volume(original)/1000,
                           'bounds_xyz_mm': [q['v'].min(0).tolist(), q['v'].max(0).tolist()]},
              'unchanged_reference_arrays': identities,
              'nose_material_missing_from_final_body_mm3': nose_missing,
              'central_roof_change': {'declared_print_facet_removed_mm3': declared_roof_removal,
                                     'unexpected_removed_mm3': unexpected_roof_removal,
                                     'unexpected_added_mm3': volume(roof_added),
                                     'unexpected_symmetric_difference_mm3': roof_difference},
              'print_facet': facet_report,
              'removed_features': removed_features(body, original),
              'shoulder_sections': shoulder_sections(body),
              'camera_fit': {'conservative_hull_body_overlap_mm3': volume(overlap),
                             'overlap_components': describe(overlap),
                             'pass': volume(overlap) <= TOL_VOLUME},
              'camera_rearward_insertion': {'continuous_sweep_length_mm': 80,
                                             'wearing_direction': [0, 1, 0],
                                             'swept_hull_body_overlap_mm3': volume(rearward_sweep),
                                             'overlap_components': describe(rearward_sweep),
                                             'pass': volume(rearward_sweep) <= TOL_VOLUME},
              'optics': optical_checks(body, camera, values),
              'retention': {'status': 'not_verified', 'strap_eyes_removed': True,
                            'band_in_printed_model': False,
                            'note': 'The rejected internal plates and strap eyes are absent. The former cinch-band retention claim no longer applies. This audit verifies the unchanged camera pose and unobstructed insertion, not secure retention during wearing or handling.'},
              'limitations': ['Geometric fit and a successful slice do not establish physical strength, comfort or print success.',
                              'The STEP camera is an open assembly surface. Its convex hull is used as a conservative occupied and insertion envelope.',
                              'The optical audit confirms physical openings and forward lens exposure; it does not certify operational field of view.',
                              'Material removal probes are interior diagnostic volumes, supplemented by full temple sections and visual inspection.']}
    print(json.dumps({key: report[key] for key in ['topology', 'removed_features', 'camera_fit', 'camera_rearward_insertion', 'optics']}, indent=2), flush=True)
    head = head_and_slots()
    report['head_fit'] = {key: head[key] for key in ['head_sha256', 'parts', 'camera_first_skin_contact',
                                                  'classification_contact_epsilon_mm', 'classification_limit',
                                                  'all_parts_sampled_penetration_within_contact_epsilon']}
    report['terminal_slots'] = head['terminal_slots']
    report['head_fit']['reused_for_identical_geometry_head_datums_and_audit_methods'] = head.get('reused_for_identical_geometry_head_datums_and_audit_methods', False)
    unchanged = all(digest(ROOT/path) == expected for path, expected in hashes.items())
    report['sources_unchanged_during_verification'] = unchanged
    report['runtime_seconds'] = time.time()-start
    report['pass'] = bool(topology_ok and all(item['all_arrays_identical'] for item in identities.values())
                          and nose_missing <= TOL_VOLUME and roof_difference <= TOL_VOLUME
                          and (facet_report is None or facet_report['pass'])
                          and report['removed_features']['pass'] and report['shoulder_sections']['pass'] and report['camera_fit']['pass']
                          and report['camera_rearward_insertion']['pass'] and report['optics']['pass']
                          and head['all_parts_sampled_penetration_within_contact_epsilon']
                          and head['terminal_slots']['all_slot_locations_and_reach_preserved'] and unchanged)
    (C / 'fit.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps({'pass': report['pass'], 'runtime_seconds': report['runtime_seconds'],
                      'source_unchanged': unchanged, 'nose_missing_mm3': nose_missing,
                      'roof_difference_mm3': roof_difference, 'retention': report['retention']}, indent=2), flush=True)
    assert report['pass'], 'Structural geometry verification failed; inspect checks/fit.json'


if __name__ == '__main__':
    main()
