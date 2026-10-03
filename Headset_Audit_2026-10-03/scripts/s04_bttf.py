"""Step 4: extract BTTF 'Normal' (build item for object 2) from the raw 3MF with own code,
and register it to wearing coordinates by the stated datum (center front face Y=0, lower edge Z=0, X centered)."""
import zipfile, json, numpy as np
import xml.etree.ElementTree as ET
from common import RAW, DATA, volume, edge_check, components
CORE = '{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}'
z = zipfile.ZipFile(RAW / 'BTTF_Glasses.3mf')
obj = ET.fromstring(z.read('3D/Objects/object_15.model'))
mesh = obj.find(f'.//{CORE}mesh')
V = np.array([[float(v.get(a)) for a in 'xyz'] for v in mesh.iter(CORE + 'vertex')])
F = np.array([[int(t.get(a)) for a in ('v1', 'v2', 'v3')] for t in mesh.iter(CORE + 'triangle')])
root = ET.fromstring(z.read('3D/3dmodel.model'))
out = {}
for item in root.iter(CORE + 'item'):
    m = np.array([float(x) for x in item.get('transform').split()]).reshape(4, 3)
    W = V @ m[:3] + m[3]
    Ff = F if np.linalg.det(m[:3]) > 0 else F[:, ::-1]
    out[item.get('objectid')] = {'size': (W.max(0) - W.min(0)).tolist(), 'det': float(np.linalg.det(m[:3])), 'volume_mm3': volume(W, Ff)}
    if item.get('objectid') == '2':
        W2, F2 = W, Ff
print(json.dumps(out, indent=1))
np.savez_compressed(DATA.parent.parent / '../tmp_unused.npz' if False else '/tmp/claude-0/-home-user-LingTouchCompanion/a3d04089-c5dd-5567-a32c-b263c145e9d4/scratchpad/bttf_build_item2.npz', v=W2, f=F2)
print('edge check', edge_check(F2))
lab, n = components(F2, len(W2)); print('components', n)

# --- register: try the axis/sign choices, keep the one whose vertices coincide with the delivered shell
from scipy.spatial import cKDTree
from common import read_3mf, FRONT_3MF
import itertools
shell = [v for k, v in read_3mf(FRONT_3MF).items() if k.endswith('_shell')][0]
tree = cKDTree(shell[0])
best = None
for sx, sy, sz in itertools.product([1, -1], repeat=3):
    P = np.stack([sx * W2[:, 1], sy * W2[:, 0], sz * W2[:, 2]], 1)
    # datum: X centered, lower edge Z=0, front-most point at center (|X|<5) is Y=0
    P[:, 0] -= (P[:, 0].max() + P[:, 0].min()) / 2
    P[:, 2] -= P[:, 2].min()
    c = np.abs(P[:, 0]) < 5
    P[:, 1] -= P[c, 1].min()
    d, _ = tree.query(P)
    frac = float((d < 1e-6).mean())
    print('signs', sx, sy, sz, 'fraction of BTTF vertices exactly on delivered shell', round(frac, 4))
    if best is None or frac > best[0]:
        best = (frac, (sx, sy, sz), P)
frac, signs, P = best
Fw = F2 if np.prod(signs) * 1 > 0 else F2[:, ::-1]
# swapping X/Y flips handedness once
Fw = Fw[:, ::-1]
vol = volume(P, Fw)
if vol < 0: Fw = Fw[:, ::-1]; vol = -vol
np.savez_compressed(DATA / 'bttf_normal_wearing.npz', v=P, f=Fw)
res = {'chosen_signs_xyz': signs, 'fraction_on_shell': frac, 'volume_cm3': vol / 1000,
       'bbox': [P.min(0).tolist(), P.max(0).tolist()], 'size': (P.max(0) - P.min(0)).tolist()}
json.dump(res, open(DATA / 'bttf_normal_wearing.json', 'w'), indent=1)
print(json.dumps(res, indent=1))
