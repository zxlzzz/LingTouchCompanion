"""Step 10d: shell surface within 3 mm of the head in the centre zone (|X|<=47.3): is the material behind each point
original BTTF (e.g. a cut face of the original) or new material? Gives the true new-material-to-nose distance."""
import json, numpy as np, trimesh
from scipy.spatial import cKDTree
from common import read_3mf, FRONT_3MF, DATA
from headdist import Head
objs = read_3mf(FRONT_3MF)
SV, SF = objs['Front_Compact_Review_shell']; HV, HF = objs['Head_reference_do_not_print']
m = trimesh.Trimesh(SV, SF, process=False)
P, fid = trimesh.sample.sample_surface(m, 1500000, seed=31); N = m.face_normals[fid]
z = (np.abs(P[:, 0]) <= 47.3) & (P[:, 1] < 40)
P, N = P[z], N[z]
head = Head(HV, HF, crop_lo=P.min(0) - 10, crop_hi=P.max(0) + 10, spacing=0.15)
d0 = head.tree.query(P)[0]
near = d0 < 3.5
P, N = P[near], N[near]
d = head.dist(P, refine=len(P))
b = np.load(DATA / 'bttf_normal_wearing.npz'); bt = trimesh.Trimesh(b['v'], b['f'], process=False)
behind = P - N * 0.05
orig_mat = bt.contains(behind)
res = {'centre_zone_points_within_3.5mm': int(len(P))}
for nm, mm in [('backed_by_original_material', orig_mat), ('backed_by_new_material', ~orig_mat)]:
    if mm.any():
        k = np.argmin(np.where(mm, d, np.inf))
        res[nm] = {'n': int(mm.sum()), 'min_distance_to_head_mm': float(d[k]), 'at': P[k].round(3).tolist()}
    else:
        res[nm] = {'n': 0}
json.dump(res, open(DATA / 'nose_new_vs_original.json', 'w'), indent=1); print(json.dumps(res, indent=1))
