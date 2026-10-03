"""Step 9b: can the REAL camera (STEP housing side silhouette, extruded over the full width = a superset of the
real housing) leave the seated pose backwards past the 0.8 mm hooks without deforming anything?
Search a grid of rigid moves: back along the camera axis (-t) by d and lift off the floor (+h) by e,
plus small rotations, and look for a collision-free connected path from the seat to d = 4 mm (past the hooks)."""
import json, math, numpy as np
import manifold3d as md
from shapely.geometry import Polygon
from shapely.ops import unary_union
from common import read_3mf, FRONT_3MF, DATA, IMG
from camframe import to_wear, HX, HH, HT, O
from render import section_image
M = md.Manifold
a = np.load(DATA / 'cs30_housing_mesh.npz'); V, F = a['v'], a['f']
# silhouette of the housing projected along X, in local (t, h)
T2 = np.stack([V[:, 2] + 25, V[:, 1] + 12.5], 1)[F]
polys = [Polygon(t) for t in T2 if abs(np.cross(t[1] - t[0], t[2] - t[0])) > 1e-9]
import shapely
sil = shapely.union_all(polys, grid_size=0.002).buffer(0)
if sil.geom_type != 'Polygon':
    sil = max(sil.geoms, key=lambda g: g.area)
ext = np.array(sil.exterior.coords)[:-1]
print('silhouette bounds t,h', ext.min(0).round(3), ext.max(0).round(3), 'area', round(sil.area, 2))
# camera prism in local (x,h,t): CrossSection in (t,h) extruded along x
cs = md.CrossSection([ext[::-1] if Polygon(ext).exterior.is_ccw is False else ext])
prism = cs.extrude(89.94)  # (t, h, x')
def pose(d=0.0, e=0.0, phi=0.0):
    """local -> wearing, with the camera moved back by d along -t, lifted by e along +h, rotated phi (deg, front up)
    about the local point (t=0,h=0)."""
    p = math.radians(phi); c, s = math.cos(p), math.sin(p)
    # in local: (t,h) -> (c t - s h - d, s t + c h + e) ; x' -> x = x' - 44.97
    # wearing = O + x HX + h HH + t HT
    R = np.zeros((3, 4))
    # columns act on prism coords (t, h, x')
    R[:, 0] = c * HT + s * HH
    R[:, 1] = -s * HT + c * HH
    R[:, 2] = HX
    R[:, 3] = O - 44.97 * HX - d * HT + e * HH
    return prism.transform(R.tolist())
shell_V, shell_F = read_3mf(FRONT_3MF)['Front_Compact_Review_shell']
shell = M(md.Mesh64(vert_properties=np.ascontiguousarray(shell_V), tri_verts=np.ascontiguousarray(shell_F, np.uint64)))
def hit(d, e, phi=0.0):
    return (pose(d, e, phi) ^ shell).volume() > 1e-5
res = {'silhouette_t_h_bounds': [ext.min(0).tolist(), ext.max(0).tolist()], 'seated_overlap_mm3': float((pose() ^ shell).volume())}
ds = np.round(np.arange(0, 4.01, 0.05), 3); es = np.round(np.arange(0, 2.01, 0.05), 3)
free = np.zeros((len(ds), len(es)), bool)
for i, d in enumerate(ds):
    for j, e in enumerate(es):
        free[i, j] = not hit(d, e)
# connectivity from (0,0)
from collections import deque
seen = np.zeros_like(free); q = deque()
if free[0, 0]: seen[0, 0] = True; q.append((0, 0))
while q:
    i, j = q.popleft()
    for di, dj in [(1, 0), (-1, 0), (0, 1), (0, -1)]:
        a2, b2 = i + di, j + dj
        if 0 <= a2 < len(ds) and 0 <= b2 < len(es) and free[a2, b2] and not seen[a2, b2]:
            seen[a2, b2] = True; q.append((a2, b2))
res['grid_d_back_mm'] = [float(ds[0]), float(ds[-1]), 0.05]
res['grid_e_lift_mm'] = [float(es[0]), float(es[-1]), 0.05]
res['seat_is_free'] = bool(free[0, 0])
res['escape_to_d4_without_deforming'] = bool(seen[-1].any())
if seen[-1].any():
    # report the minimal lift needed along the way: path through max over d of minimal reachable e
    need = []
    for i in range(len(ds)):
        js = np.where(seen[i])[0]
        need.append(float(es[js.min()]) if len(js) else None)
    res['min_lift_reachable_at_each_d'] = dict(zip([float(x) for x in ds[::4]], need[::4]))
# free travel straight back for the real silhouette (no lift)
k = 0
while k + 1 < len(ds) and free[k + 1, 0]: k += 1
res['straight_back_free_mm_real_silhouette'] = float(ds[k])
k = 0
while k + 1 < len(es) and free[0, k + 1]: k += 1
res['lift_free_mm_real_silhouette'] = float(es[k])
np.savez_compressed(DATA / 'hook_escape_grid.npz', ds=ds, es=es, free=free, reach=seen)
json.dump(res, open(DATA / 'hook_escape.json', 'w'), indent=1)
print(json.dumps(res, indent=1))
