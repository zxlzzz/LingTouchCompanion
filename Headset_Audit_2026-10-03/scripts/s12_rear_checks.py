"""Step 12: rear part numbers from the delivered mesh (own ray casts / sections)."""
import json, math, numpy as np
import trimesh
from trimesh.ray.ray_pyembree import RayMeshIntersector
from shapely.geometry import Point, Polygon, LineString
from shapely.ops import unary_union, polygonize
from common import read_3mf, REAR_3MF, FRONT_3MF, DATA, section_segments
objs = read_3mf(REAR_3MF)
SV, SF = [v for k, v in objs.items() if k.endswith('_shell')][0]
BV, BF = [v for k, v in objs.items() if 'occupant' in k][0]
mesh = trimesh.Trimesh(SV, SF, process=False); ray = RayMeshIntersector(mesh)
def add(a, b):
    return None if a is None or b is None else a + b
def first_hit(o, d):
    loc, idx, _ = ray.intersects_location(np.array([o], float), np.array([d], float) / np.linalg.norm(d), multiple_hits=False)
    return None if len(loc) == 0 else float(np.linalg.norm(loc[0] - o))
res = {}
c = np.array([0, 217.0, 39.2])
bc = (BV.max(0) + BV.min(0)) / 2; res['battery_reference'] = {'center': bc.round(3).tolist(), 'length_x': float(np.ptp(BV[:, 0])), 'diameter_yz': [float(np.ptp(BV[:, 1])), float(np.ptp(BV[:, 2]))]}
# cavity size by rays from the battery axis
cav = {}
for z in [30.13, 35.13, 39.2, 43.13]:
    for x in [-35.13, -0.37, 0.37, 20.13, 35.13]:
        o = np.array([x, 217.0, z])
        cav[f'x{x}_z{z}'] = {'front_to_back_Y': add(first_hit(o, [0, -1, 0]), first_hit(o, [0, 1, 0]))}
    o = np.array([0.0, 217.0, z]); cav[f'z{z}_end_to_end_X (None = ray leaves through the +X port notch)'] = add(first_hit(o, [-1, 0, 0]), first_hit(o, [1, 0, 0]))
o = np.array([0.13, 217.0, 33.13]); cav['floor_to_axis_from_z33'] = first_hit(o, [0, 0, -1])
cav['up_from_cavity_hits_anything'] = {f'x{x}': first_hit(np.array([x, 217.0, 30.0]), [0, 0, 1]) for x in [-40.13, -20.13, 0.13, 20.13, 40.13]}
res['cavity'] = cav
# catches: section at several X, take the shell polygon(s) and measure the battery circle clearance when the battery
# sits against the FRONT wall (worst case) and is lifted until it touches; overlap = how much it is held.
def section_polys(x):
    s = np.round(section_segments(SV, SF, 0, x)[:, :, 1:], 6)
    lines = [LineString(seg) for seg in s]
    polys = list(polygonize(unary_union(lines)))
    # even-odd fill: XOR of all loops gives the material region
    region = polys[0]
    for q in polys[1:]: region = region.symmetric_difference(q)
    return region, s.reshape(-1, 2)
catch = {}
for x in [-42.13, -36.13, -29.13, -22.13, -16.13, 16.13, 22.13, 29.13, 36.13, 42.13, -8.13, 0.37, 8.13]:
    P, pts = section_polys(x)
    back = pts[(pts[:, 0] > 222) & (pts[:, 1] > 43.5) & (pts[:, 1] < 46.5)]
    tip_y = float(back[:, 0].min()) if len(back) else None
    # worst case: battery pushed to the front wall (min centre y); find max lift before touching any material
    front_inner = min([q[0] for q in pts if 204 < q[0] < 207 and 30 < q[1] < 50] or [205.3])
    yc = front_inner + 11.4
    z = 39.2; free = True; step = 0.01; lift = 0.0
    while lift < 15:
        circ = Point(yc, 39.2 + lift + step).buffer(11.4, 256)
        if circ.intersection(P).area > 1e-6:
            break
        lift += step
    catch[f'x={x}'] = {'hook_tip_y': tip_y, 'front_inner_wall_y': front_inner, 'battery_centre_y_worst': yc,
                       'overlap_vs_hook_mm (11.4 - (tip - yc))': None if tip_y is None else round(11.4 - (tip_y - yc), 3),
                       'free_lift_before_contact_mm': round(lift, 2)}
res['catches_section_check'] = catch
# strap plates and slot
for side, xs in [('left', -45.03), ('right', 45.03)]:
    o = np.array([xs, 199.8, 41.5])
    up = first_hit(o, [0, 0, 1]); dn = first_hit(o, [0, 0, -1])
    fy = first_hit(o, [0, -1, 0]); by = first_hit(o, [0, 1, 0])
    res[f'slot_{side}'] = {'slot_z': [41.5 - dn, 41.5 + up], 'slot_height': up + dn, 'slot_y': [199.8 - fy, 199.8 + by], 'slot_width_y': fy + by,
                           'material_below_slot': (41.5 - dn) - SV[np.abs(SV[:, 0] - xs) < 1.6][:, 2].min(),
                           'material_above_slot': SV[np.abs(SV[:, 0] - xs) < 1.6][:, 2].max() - (41.5 + up)}
# bottom plane: lowest Z for each X strip, and any downward-facing face above the base that faces the bed
fn = mesh.face_normals; cz = SV[SF].mean(1)[:, 2]
down = fn[:, 2] < -0.99
res['bottom'] = {'min_z': float(SV[:, 2].min()), 'downward_flat_faces_z_values': sorted(set(np.round(cz[down], 3).tolist()))[:30],
                 'downward_area_at_base_mm2': float(mesh.area_faces[down & (np.abs(cz - SV[:, 2].min()) < 1e-3)].sum())}
strips = {}
for x0 in np.arange(-47.5, 47.5, 2.5):
    m = (SV[:, 0] >= x0) & (SV[:, 0] < x0 + 2.5)
    strips[f'{x0:.1f}'] = float(SV[m, 2].min()) if m.any() else None
res['bottom']['lowest_z_per_2.5mm_x_strip'] = strips
# front ear tab slot (front part), measured the same way
FV, FF = read_3mf(FRONT_3MF)['Front_Compact_Review_shell']
fm = trimesh.Trimesh(FV, FF, process=False); fr = RayMeshIntersector(fm)
def fhit(o, d):
    loc, idx, _ = fr.intersects_location(np.array([o], float), np.array([d], float), multiple_hits=False)
    return None if len(loc) == 0 else float(np.linalg.norm(loc[0] - o))
tabs = {}
for xs in [-69.4, 69.4]:
    # find a point inside the slot: scan Y 150-158 at Z 39.2 for an X-ray that passes through
    for y in np.arange(150.0, 158.0, 0.1):
        o = np.array([xs * 1.2, y, 39.2])
        if fhit(o, [-np.sign(xs), 0, 0]) is None or fhit(o, [-np.sign(xs), 0, 0]) > 30:
            o2 = np.array([xs, y, 39.2]); up = fhit(o2, [0, 0, 1]); dn = fhit(o2, [0, 0, -1])
            fy = fhit(o2, [0, -1, 0]); by = fhit(o2, [0, 1, 0])
            tabs[f'x{xs}'] = {'slot_z': [39.2 - dn, 39.2 + up], 'slot_y': [y - fy, y + by], 'centre_z': 39.2 + (up - dn) / 2}
            break
res['front_tab_slots'] = tabs
json.dump(res, open(DATA / 'rear_checks.json', 'w'), indent=1)
print(json.dumps(res, indent=1))
