"""Step 8: camera insertion path over the FULL camera width (89.94), against the delivered shell.
Path: camera flat (bottom Z = pivot Z), pushed horizontally from the face side (+Y) to the stop,
then rotated about the rear-lower edge, front down, 0 -> 20 deg. Boxes are the 89.94 x 30 x 25 envelope.
All collisions are reported with their location; the ones at the hooks/spring tongues are listed apart."""
import json, math, numpy as np
import manifold3d as md
from common import read_3mf, FRONT_3MF, DATA
from camframe import PY, PZ
M = md.Manifold
def man(V, F):
    m = M(md.Mesh64(vert_properties=np.ascontiguousarray(V, float), tri_verts=np.ascontiguousarray(F, np.uint64)))
    assert m.status() == md.Error.NoError; return m
def box(lo, hi):
    lo = np.array(lo, float); hi = np.array(hi, float); return M.cube(tuple(hi - lo)).translate(tuple(lo))
shell = man(*read_3mf(FRONT_3MF)['Front_Compact_Review_shell'])
W, H, T = 89.94, 30.0, 25.0
def cam_at(theta_deg, dy=0.0):
    """camera pose: rotated front-down by theta about the rear-lower edge, then shifted by dy along +Y."""
    th = math.radians(theta_deg); c, s = math.cos(th), math.sin(th)
    # local (x, h, t) -> wearing: h-axis (0,-s,c), t-axis (0,-c,-s)
    A = [[1, 0, 0, 0], [0, -s, -c, PY + dy], [0, c, -s, PZ]]
    return box([-W / 2, 0, 0], [W / 2, H, T]).transform(A)
def report(name, inter):
    v = inter.volume()
    out = {'collision_volume_mm3': float(v)}
    if v > 1e-6:
        parts = []
        for p in inter.decompose():
            if p.volume() < 1e-7: continue
            mm = p.to_mesh64(); vv = np.array(mm.vert_properties)[:, :3]
            parts.append({'volume_mm3': float(p.volume()), 'bbox_min': vv.min(0).round(3).tolist(), 'bbox_max': vv.max(0).round(3).tolist()})
        out['pieces'] = sorted(parts, key=lambda q: -q['volume_mm3'])[:20]
    return out
res = {}
# 1) horizontal push: union of the flat camera over Y from the stop to far behind (exact: a prism)
flat_long = box([-W / 2, PY - T, PZ], [W / 2, 260, PZ + H])
res['horizontal_push_full_width'] = report('push', flat_long ^ shell)
# same with 0.3 mm extra top/bottom margin removed (exact camera only) is the line above; also check thin slices at the ends
for xa, xb in [(-44.97, -40), (40, 44.97), (-5, 5)]:
    res[f'horizontal_push_x_{xa}_{xb}'] = report('', box([xa, PY - T, PZ], [xb, 260, PZ + H]) ^ shell)
# 2) rotation: union of poses every 0.1 deg (exact boxes), plus the convex hull between consecutive poses
poses = [cam_at(a) for a in np.arange(0, 20.0001, 0.1)]
hulls = [M.batch_hull([poses[i], poses[i + 1]]) for i in range(len(poses) - 1)]
rot = M.batch_boolean(hulls, md.OpType.Add)
res['rotation_0_to_20_full_width'] = report('rot', rot ^ shell)
# 3) final pose clearance to the shell (exact): grow test
final = cam_at(20)
res['final_pose_overlap'] = report('final', final ^ shell)
# 4) how far can the seated camera move before touching the shell (excluding nothing): along +h (lift off floor), -t (back), +Y
th = math.radians(20); hdir = np.array([0, -math.sin(th), math.cos(th)]); tdir = np.array([0, -math.cos(th), -math.sin(th)])
def free_travel(direction, maxd=5.0, step=0.01):
    d = 0.0
    while d < maxd:
        m = final.translate(tuple(direction * (d + step)))
        if (m ^ shell).volume() > 1e-6: return d
        d += step
    return d
res['seated_free_travel_mm'] = {'lift_perpendicular_to_floor_+h': free_travel(hdir), 'straight_back_along_axis_-t': free_travel(-tdir),
                                'straight_back_+Y': free_travel(np.array([0, 1.0, 0])), 'sideways_+X': free_travel(np.array([1.0, 0, 0])), 'sideways_-X': free_travel(np.array([-1.0, 0, 0]))}
json.dump(res, open(DATA / 'insertion_check.json', 'w'), indent=1)
print(json.dumps(res, indent=1))
