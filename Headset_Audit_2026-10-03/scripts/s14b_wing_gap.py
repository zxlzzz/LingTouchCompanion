"""Step 14b: the slit between the camera-box end wall and the wing on the front face; and new material below the floor plane (exact check)."""
import json, numpy as np, trimesh
from trimesh.ray.ray_pyembree import RayMeshIntersector
from common import read_3mf, FRONT_3MF, DATA
from camframe import HH, PY, PZ
SV, SF = read_3mf(FRONT_3MF)['Front_Compact_Review_shell']
mesh = trimesh.Trimesh(SV, SF, process=False); ray = RayMeshIntersector(mesh)
res = {}
for sgn in [-1, 1]:
    for z in [14.13, 18.13, 22.13, 26.13, 30.13, 34.13, 38.13, 42.13, 44.13, 46.13]:
        xs = np.arange(46.9, 48.6, 0.005)
        O = np.stack([sgn * xs, np.full(len(xs), -60.0), np.full(len(xs), z)], 1)
        l, idx, _ = ray.intersects_location(O, np.tile([0, 1.0, 0], (len(O), 1)), multiple_hits=False)
        y = np.full(len(xs), np.nan); y[idx] = l[:, 1]
        deep = (y > -5) | np.isnan(y)
        if deep.any():
            res[f'{"+" if sgn > 0 else "-"}X z={z}'] = {'gap_x_from': float(xs[deep].min()), 'gap_x_to': float(xs[deep].max()), 'width_mm': float(xs[deep].max() - xs[deep].min() + 0.005),
                                                       'first_hit_behind_gap_Y': float(np.nanmin(y[deep])) if (~np.isnan(y[deep])).any() else None}
        else:
            res[f'{"+" if sgn > 0 else "-"}X z={z}'] = 'closed'
# exact: new material below the camera bottom plane in the wing zone
b = np.load(DATA / 'bttf_normal_wearing.npz'); bt = trimesh.Trimesh(b['v'], b['f'], process=False)
P, _ = trimesh.sample.sample_surface(mesh, 1500000, seed=5)
w = (np.abs(P[:, 0]) > 47.3) & (np.abs(P[:, 0]) <= 65)
hh = (P - np.array([0, PY, PZ])) @ HH
cand = P[w & (hh < -0.01)]
from scipy.spatial import cKDTree
bs, _ = trimesh.sample.sample_surface(bt, 4000000, seed=2)
dk = cKDTree(bs).query(cand)[0]
flag = cand[dk > 0.12]
d = np.concatenate([trimesh.proximity.closest_point(bt, flag[i:i + 4000])[1] for i in range(0, len(flag), 4000)]) if len(flag) else np.zeros(0)
inside = bt.contains(flag) if len(flag) else np.zeros(0, bool)
keep = (d > 0.02) & ~inside
newpts = flag[keep]
res['wing_zone_samples_below_camera_bottom_plane'] = int(len(cand))
res['of_which_not_on_original_surface_and_outside_original'] = int(len(newpts))
if len(newpts):
    res['those_bbox'] = [newpts.min(0).round(2).tolist(), newpts.max(0).round(2).tolist()]
    res['max_dist_from_original_mm'] = float(d[keep].max())
json.dump(res, open(DATA / 'wing_gap_and_floor.json', 'w'), indent=1); print(json.dumps(res, indent=1))

# height of those new points relative to the floor-wall OUTER plane (h = -2.5, used by the generator) and inner/camera plane (h = 0)
if len(newpts):
    h_new = (newpts - np.array([0, PY, PZ])) @ HH
    res['new_below_plane_h0_min_h'] = float(h_new.min())
    below_outer = newpts[h_new < -2.5 - 0.01]
    res['new_points_below_outer_floor_plane_h-2.5'] = int(len(below_outer))
    if len(below_outer):
        res['below_outer_bbox'] = [below_outer.min(0).round(2).tolist(), below_outer.max(0).round(2).tolist()]
        res['below_outer_deepest_mm'] = float(-(h_new.min() + 2.5))
        res['below_outer_deepest_at'] = newpts[h_new.argmin()].round(2).tolist()
    json.dump(res, open(DATA / 'wing_gap_and_floor.json', 'w'), indent=1)
    print({k: v for k, v in res.items() if k.startswith('new_') or k.startswith('below')})
