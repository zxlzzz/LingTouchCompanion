"""Step 14: front part - top plane, camera exposure other than the front, wing limits, flat cut behind the camera."""
import json, math, numpy as np
import trimesh
from trimesh.ray.ray_pyembree import RayMeshIntersector
from PIL import Image, ImageDraw, ImageFont
from common import read_3mf, FRONT_3MF, DATA, IMG
from camframe import to_wear, HX, HH, HT, PY, PZ
objs = read_3mf(FRONT_3MF)
SV, SF = objs['Front_Compact_Review_shell']
mesh = trimesh.Trimesh(SV, SF, process=False); ray = RayMeshIntersector(mesh)
res = {}
# ---- top plane: highest shell point in each 0.25 mm XY cell (ray from above)
g = 0.25
xs = np.arange(-72, 72, g) + g / 2; ys = np.arange(-35, 160, g) + g / 2
X, Y = np.meshgrid(xs, ys); O = np.stack([X.ravel(), Y.ravel(), np.full(X.size, 80.0)], 1)
loc, idx, _ = ray.intersects_location(O, np.tile([0, 0, -1.0], (len(O), 1)), multiple_hits=False)
top = np.full(len(O), np.nan); top[idx] = loc[:, 2]
cell = g * g; has = ~np.isnan(top)
at_top = has & (top > 57.13); low = has & (top <= 57.13)
res['top'] = {'plan_area_mm2': float(has.sum() * cell), 'area_at_Z57.14_mm2': float(at_top.sum() * cell),
              'area_lower_mm2': float(low.sum() * cell)}
# where the upper edge is lower: classify by region
reg = {}
for name, m in [('camera_zone |X|<=47.3', np.abs(O[:, 0]) <= 47.3), ('wings 47.3<|X|<=65', (np.abs(O[:, 0]) > 47.3) & (np.abs(O[:, 0]) <= 65)),
                ('arms |X|>65, Y<75', (np.abs(O[:, 0]) > 65) & (O[:, 1] < 75)), ('arms |X|>65, Y 75-140', (np.abs(O[:, 0]) > 65) & (O[:, 1] >= 75) & (O[:, 1] < 140)),
                ('ear tabs Y>=140', O[:, 1] >= 140)]:
    hm = has & m
    reg[name] = {'plan_area_mm2': float(hm.sum() * cell), 'at_57.14_mm2': float((hm & at_top).sum() * cell),
                 'lower_top_heights_seen': sorted(set(np.round(top[hm & low], 1).tolist()))[-8:]}
res['top']['by_region'] = reg
# image: top height map
img = np.full((len(ys), len(xs), 3), 255, np.uint8)
T = top.reshape(len(ys), len(xs))
img[T > 57.13] = (40, 150, 165)
img[(T <= 57.13) & (T > 55.0)] = (230, 120, 0)
img[(T <= 55.0)] = (200, 30, 30)
im = Image.fromarray(img[::-1, ::-1] if False else img).resize((len(xs) * 2, len(ys) * 2), Image.NEAREST)
im = im.transpose(Image.FLIP_TOP_BOTTOM).transpose(Image.FLIP_TOP_BOTTOM)
dr = ImageDraw.Draw(im); f = ImageFont.load_default(size=16)
dr.text((10, 10), 'Top height map (plan view, -Y at top). teal = Z 57.14 flat top; orange = 55.0-57.13; red = below 55.0', fill=(0, 0, 0), font=f)
for yy in [0, 50, 100, 150]:
    py = int((yy + 35) / g * 2); dr.line([(0, py), (30, py)], fill=(0, 0, 0)); dr.text((32, py - 8), f'Y={yy}', fill=(0, 0, 0), font=f)
im.save(IMG / 'front_top_height_map.png')
# ---- camera exposure through faces other than front (bottom/top/ends), straight out along the face normal
def face_exposure(name, pts, normal, cone_deg=0):
    dirs = [normal]
    vis = ~ray.intersects_any(pts + normal * 1e-3, np.tile(normal, (len(pts), 1)))
    return vis
step = 0.1
xg = np.arange(-44.97 + step / 2, 44.97, step)
tg = np.arange(step / 2, 25, step); hg = np.arange(step / 2, 30, step)
exp = {}
A, B = np.meshgrid(xg, tg); P = to_wear(A.ravel(), 0.0, B.ravel())
v = face_exposure('bottom', P, -HH); exp['bottom_face_straight_down_normal'] = {'exposed_mm2': float(v.sum() * step * step),
    'exposed_x_t_bbox': [[float(A.ravel()[v].min()), float(B.ravel()[v].min())], [float(A.ravel()[v].max()), float(B.ravel()[v].max())]] if v.any() else None}
np.savez_compressed(DATA / 'camera_bottom_exposure.npz', x=A.ravel(), t=B.ravel(), vis=v)
vz = ~ray.intersects_any(P - np.array([0, 0, 1e-3]), np.tile([0, 0, -1.0], (len(P), 1)))
exp['bottom_face_seen_from_straight_below_-Z'] = float(vz.sum() * step * step)
# split the bottom exposure: thin U-slots vs larger holes (cells whose 1 mm neighbourhood is fully exposed)
Vm = v.reshape(A.shape)
from scipy.ndimage import binary_erosion, label
core = binary_erosion(Vm, np.ones((5, 5)))
lab, n = label(Vm)
blobs = []
for k in range(1, n + 1):
    m = lab == k
    blobs.append({'area_mm2': float(m.sum() * step * step), 'x_range': [float(A[m].min()), float(A[m].max())], 't_range': [float(B[m].min()), float(B[m].max())],
                  'centre_wearing': to_wear(A[m].mean(), 0, B[m].mean()).round(2).tolist()})
exp['bottom_exposed_blobs'] = sorted(blobs, key=lambda b: -b['area_mm2'])[:10]
A, B = np.meshgrid(xg, tg); P = to_wear(A.ravel(), 30.0, B.ravel())
v = face_exposure('top', P, HH); exp['top_face_up_normal_mm2'] = float(v.sum() * step * step)
vz = ~ray.intersects_any(P + np.array([0, 0, 1e-3]), np.tile([0, 0, 1.0], (len(P), 1))); exp['top_face_seen_from_above_+Z_mm2'] = float(vz.sum() * step * step)
for sgn in [-1, 1]:
    A, B = np.meshgrid(hg, tg); P = to_wear(sgn * 44.97, A.ravel(), B.ravel())
    v = face_exposure('end', P, sgn * HX); exp[f'end_face_{"+X" if sgn > 0 else "-X"}_mm2'] = float(v.sum() * step * step)
res['camera_exposure_other_faces'] = exp
# ---- wings: new material below the camera floor plane (outer bottom plane h=-2.5 in the delivered script; brief: 'camera bottom wall plane')
b = np.load(DATA / 'bttf_normal_wearing.npz')
bt = trimesh.Trimesh(b['v'], b['f'], process=False)
Pw, fid = trimesh.sample.sample_surface(mesh, 1500000, seed=5)
wing = (np.abs(Pw[:, 0]) > 47.3) & (np.abs(Pw[:, 0]) <= 65)
# is the sample on new material? (not on the original BTTF surface)
from scipy.spatial import cKDTree
bs, _ = trimesh.sample.sample_surface(bt, 3000000, seed=2)
onorig = cKDTree(bs).query(Pw[wing])[0] < 0.15
Q = Pw[wing][~onorig]
hh = (Q - np.array([0, PY, PZ])) @ HH       # height above the camera bottom plane (h=0) in the camera frame
res['wings'] = {'new_surface_samples': int(len(Q)), 'min_height_above_camera_bottom_plane_h0': float(hh.min()),
                'min_height_above_floor_outer_plane_h-2.5': float(hh.min() + 2.5),
                'lowest_new_point': Q[hh.argmin()].round(2).tolist()}
# flush at |X| = 47.3: front-most point of wing vs camera front wall outer surface (t = 27 plane) along Z
fl = {}
for sgn in [-1, 1]:
    for z in [20.13, 25.13, 30.13, 35.13, 40.13, 45.13]:
        row = {}
        for xx in [47.0, 47.6, 48.5]:
            o = np.array([sgn * xx, -60.0, z]); l, _, _ = ray.intersects_location(o[None], np.array([[0, 1.0, 0]]), multiple_hits=False)
            row[f'|X|={xx}'] = float(l[0][1]) if len(l) else None
        # camera front wall outer plane at this z: t=27 -> point with h s.t. Z=z
        # solve: Z = PZ + h*C - 27*S  -> h; then Y
        C, S_ = math.cos(math.radians(20)), math.sin(math.radians(20))
        h = (z - PZ + 27 * S_) / C; row['front_wall_outer_plane_Y'] = float(PY - S_ * h - C * 27)
        fl[f'{"+" if sgn > 0 else "-"}X z={z}'] = row
res['wing_flush_check_front_Y'] = fl
json.dump(res, open(DATA / 'front_misc.json', 'w'), indent=1)
print(json.dumps(res, indent=1))
