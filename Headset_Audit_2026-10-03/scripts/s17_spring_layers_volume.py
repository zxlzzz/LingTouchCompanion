"""Step 17: (a) room under the front spring tongues + hooks for their 1.4 mm travel; (b) double wall in the wings;
(c) where the new material volume sits."""
import json, math, numpy as np, trimesh
import manifold3d as md
from trimesh.ray.ray_pyembree import RayMeshIntersector
from common import read_3mf, FRONT_3MF, DATA
from camframe import HX, HH, HT, PY, PZ, to_wear
SV, SF = read_3mf(FRONT_3MF)['Front_Compact_Review_shell']
mesh = trimesh.Trimesh(SV, SF, process=False); ray = RayMeshIntersector(mesh)
res = {}
# (a) tongue lower surface: local h = -1.5 for t in [-1, 13], x in [x0-3, x0+3]; hook lower face same h.
def sag(t, delta=1.4):
    q = np.clip((13 - t) / 14, 0, 1); return delta * q * q * (3 - q) / 2
spring = {}
for x0 in [-30, 30]:
    xs = np.linspace(x0 - 2.9, x0 + 2.9, 30); ts = np.linspace(-0.95, 12.9, 120)
    Xg, Tg = np.meshgrid(xs, ts); X = Xg.ravel(); T = Tg.ravel()
    P = to_wear(X, -1.5 - 1e-3, T)          # just below the tongue underside
    d = -HH
    loc, idx, _ = ray.intersects_location(P, np.tile(d, (len(P), 1)), multiple_hits=False)
    room = np.full(len(P), np.inf); room[idx] = np.linalg.norm(loc - P[idx], axis=1)
    need = sag(T)
    short = room < need
    # also the hook's rear face moving down: rear face at t=-1, h from -1.5 to 0.8 sweeps down -> check the strip behind
    spring[f'x0={x0}'] = {'min_room_minus_need_mm': float(np.min(room - need)), 'points_short_of_room': int(short.sum()),
                          'min_room_at_free_end_t<0': float(room[T < 0].min()), 'need_at_free_end': float(need[T < 0].max())}
res['front_spring_travel'] = spring
# (b) double wall: rays from the front (+Y direction) through the wing zone; list solid intervals along the ray
lay = {}
for x in [-60.13, -55.13, -52.13, 52.13, 55.13, 60.13]:
    for z in [20.13, 30.13, 40.13, 50.13]:
        o = np.array([x, -80.0, z])
        loc, idx, tri = ray.intersects_location(o[None], np.array([[0, 1.0, 0]]), multiple_hits=True)
        ys = np.sort(loc[:, 1])
        ys = ys[ys < 40]
        ints = [(round(float(ys[i]), 2), round(float(ys[i + 1]), 2)) for i in range(0, len(ys) - 1, 2)]
        lay[f'x={x},z={z}'] = {'solid_intervals_Y': ints, 'walls': len(ints),
                               'air_gap_between_first_two_walls_mm': round(float(ints[1][0] - ints[0][1]), 2) if len(ints) >= 2 else None}
res['wing_layers_along_+Y'] = lay
# (c) new material by region
a = np.load(DATA / 'front_new_material.npz')
nm = md.Manifold(md.Mesh64(vert_properties=np.ascontiguousarray(a['v']), tri_verts=np.ascontiguousarray(a['f'], np.uint64)))
def box(lo, hi):
    lo = np.array(lo, float); hi = np.array(hi, float); return md.Manifold.cube(tuple(hi - lo)).translate(tuple(lo))
reg = {'camera box zone |X|<=47.3, Y<=2.6': box([-47.3, -60, -10], [47.3, 2.6, 70]),
       'behind camera |X|<=47.3, Y>2.6 (top plate over frame, tongues etc.)': box([-47.3, 2.6, -10], [47.3, 200, 70]),
       'wings 47.3<|X|<=65': box([47.3, -60, -10], [65, 200, 70]) + box([-65, -60, -10], [-47.3, 200, 70]),
       'arms/ear tabs |X|>65': box([65, -60, -10], [80, 200, 70]) + box([-80, -60, -10], [-65, 200, 70])}
res['new_material_cm3_by_region'] = {k: round((nm ^ b).volume() / 1000, 3) for k, b in reg.items()}
res['new_material_cm3_total'] = nm.volume() / 1000
json.dump(res, open(DATA / 'spring_layers_volume.json', 'w'), indent=1); print(json.dumps(res, indent=1))
