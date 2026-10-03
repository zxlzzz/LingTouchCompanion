"""Step 15: strap route. Straight band (as modelled) from the front ear-tab slot to the rear strap-plate slot,
checked against the head cross-sections at every Z the 25 mm band covers. Also how far the head bulges past
the straight line (i.e. how the band would actually have to wrap)."""
import json, numpy as np
from shapely.geometry import LineString, Polygon, Point
from shapely.ops import polygonize, unary_union
from common import read_3mf, FRONT_3MF, DATA, IMG, section_segments
from render import section_image
HV, HF = read_3mf(FRONT_3MF)['Head_reference_do_not_print']
FV, FF = read_3mf(FRONT_3MF)['Front_Compact_Review_shell']
from common import REAR_3MF
RV, RF = [v for k, v in read_3mf(REAR_3MF).items() if k.endswith('_shell')][0]
import trimesh
from trimesh.ray.ray_pyembree import RayMeshIntersector
hray = RayMeshIntersector(trimesh.Trimesh(HV, HF, process=False))
res = {}
for side in [-1, 1]:
    A = np.array([side * 71.15665, 154.5703, 39.2])   # outer face of the ear tab, at the slot (as modelled: strap leaves the tab here)
    B = np.array([side * 46.5, 198.3, 41.5])        # outer face of the rear strap plate at the slot front edge
    out = []
    for dz in np.arange(-12.5, 12.51, 2.5):
        z = (A[2] + B[2]) / 2 + dz
        s = section_segments(HV, HF, 2, z)[:, :, :2]
        pts = s.reshape(-1, 2)
        a, b = np.r_[A[:2], z], np.r_[B[:2], z]
        dirv = (b - a) / np.linalg.norm(b - a)
        loc, _, _ = hray.intersects_location(a[None], dirv[None], multiple_hits=True)
        hits = sorted([float(np.linalg.norm(q - a)) for q in loc if np.linalg.norm(q - a) <= np.linalg.norm(b - a)])
        inside_len = sum(hits[i + 1] - hits[i] for i in range(0, len(hits) - 1, 2)) if len(hits) >= 2 else 0.0
        d = (B[:2] - A[:2]) / np.linalg.norm(B[:2] - A[:2])
        nrm = np.array([-d[1], d[0]]); nrm = nrm if nrm @ (A[:2] - np.array([0, 110])) > 0 else -nrm
        tpar = (pts - A[:2]) @ d; L = np.linalg.norm(B[:2] - A[:2])
        m = (tpar > 0) & (tpar < L)
        bulge = float(((pts[m] - A[:2]) @ nrm).max()) if m.any() else None
        inter = type('x', (), {'length': inside_len})()
        out.append({'z': round(float(z), 2), 'line_inside_head_length_mm': round(float(inter.length), 2), 'head_beyond_line_mm': None if bulge is None else round(bulge, 2)})
    res['left' if side < 0 else 'right'] = {'A_front_tab': A.tolist(), 'B_rear_plate': B.tolist(), 'straight_length_mm': float(np.linalg.norm(B - A)), 'by_z': out}
# picture: section at the strap centre height
z = 40.35
layers = []
for (V, F), rgb, lab in [((HV, HF), (90, 90, 90), 'head'), ((FV, FF), (20, 120, 140), 'front shell'), ((RV, RF), (20, 160, 90), 'rear shell')]:
    s = section_segments(V, F, 2, z); layers.append((s[:, :, :2], rgb, lab))
strap = []
for side in [-1, 1]:
    strap.append([[side * 71.15665, 154.5703], [side * 46.5, 198.3]])
layers.append((np.array(strap), (230, 30, 30), 'straight strap (as modelled)'))
section_image(layers, IMG / 'strap_route_Z40.png', 'X', 'Y', f'strap route vs head, section Z={z}', extent=[[-95, 60], [95, 235]], grid=10)
json.dump(res, open(DATA / 'strap_route.json', 'w'), indent=1); print(json.dumps(res, indent=1))
