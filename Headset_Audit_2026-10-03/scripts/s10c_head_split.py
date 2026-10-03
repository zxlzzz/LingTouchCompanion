"""Step 10c: shell surface points split into 'original BTTF skin' vs 'new skin' (distance to the original surface),
then head distance / inside per class. Avoids zero-thickness boolean films."""
import json, time, numpy as np, trimesh
from scipy.spatial import cKDTree
from common import read_3mf, FRONT_3MF, DATA
from headdist import Head
t0 = time.time()
objs = read_3mf(FRONT_3MF)
SV, SF = objs['Front_Compact_Review_shell']; HV, HF = objs['Head_reference_do_not_print']
b = np.load(DATA / 'bttf_normal_wearing.npz'); bt = trimesh.Trimesh(b['v'], b['f'], process=False)
P, _ = trimesh.sample.sample_surface(trimesh.Trimesh(SV, SF, process=False), 600000, seed=21)
bs, _ = trimesh.sample.sample_surface(bt, 4000000, seed=22)
dk = cKDTree(np.vstack([bs, bt.vertices])).query(P)[0]
cand = np.where(dk < 0.2)[0]
de = np.concatenate([trimesh.proximity.closest_point(bt, P[cand[i:i + 5000]])[1] for i in range(0, len(cand), 5000)])
d_orig = np.full(len(P), np.inf); d_orig[cand] = de
orig = d_orig < 0.01
print('classified', time.time() - t0, flush=True)
head = Head(HV, HF, crop_lo=P.min(0) - 10, crop_hi=P.max(0) + 10, spacing=0.2)
ins = head.inside(P)
dh = head.dist(P, refine=20000)
res = {'samples': int(len(P)), 'on_original_skin': int(orig.sum()), 'new_skin': int((~orig).sum())}
for nm, m in [('original_skin', orig), ('new_skin', ~orig)]:
    r = {'min_distance_to_head_mm': float(dh[m].min()), 'at': P[m][dh[m].argmin()].round(3).tolist(), 'samples_inside_head': int((m & ins).sum())}
    q = P[m & ins]
    if len(q):
        r['inside_bbox'] = [q.min(0).round(2).tolist(), q.max(0).round(2).tolist()]
        k = np.argsort(-dh[m & ins])[:3000]
        cp, dd, _ = trimesh.proximity.closest_point(head.mesh, q[k])
        r['max_penetration_mm'] = float(dd.max()); r['deepest_at'] = q[k][dd.argmax()].round(3).tolist()
        # cluster summary by Y bands
        r['inside_by_region'] = {}
        for lab, mm in [('|X|<=47.3', np.abs(q[:, 0]) <= 47.3), ('47.3<|X|<=65', (np.abs(q[:, 0]) > 47.3) & (np.abs(q[:, 0]) <= 65)),
                        ('|X|>65, Y<140', (np.abs(q[:, 0]) > 65) & (q[:, 1] < 140)), ('|X|>65, Y>=140 (ear tabs)', (np.abs(q[:, 0]) > 65) & (q[:, 1] >= 140))]:
            if mm.any(): r['inside_by_region'][lab] = {'n': int(mm.sum()), 'bbox': [q[mm].min(0).round(2).tolist(), q[mm].max(0).round(2).tolist()]}
    res[nm] = r
    np.save(DATA / f'head_inside_{nm}.npy', q)
nose = (~orig) & (np.abs(P[:, 0]) < 30) & (P[:, 2] < 45) & (P[:, 1] < 30)
res['new_skin_nose_zone(|X|<30,Z<45,Y<30)'] = {'min_distance_mm': float(dh[nose].min()), 'at': P[nose][dh[nose].argmin()].round(3).tolist(), 'samples': int(nose.sum())}
# new skin within 2 mm of the head anywhere, outside the ear-tab/arm zone
close = (~orig) & (dh < 2.0)
res['new_skin_within_2mm_of_head'] = {'n': int(close.sum())}
if close.any():
    q = P[close]
    res['new_skin_within_2mm_of_head']['by_region'] = {lab: int(mm.sum()) for lab, mm in [('|X|<=47.3', np.abs(q[:, 0]) <= 47.3), ('47.3<|X|<=65', (np.abs(q[:, 0]) > 47.3) & (np.abs(q[:, 0]) <= 65)), ('|X|>65', np.abs(q[:, 0]) > 65)]}
res['seconds'] = time.time() - t0
json.dump(res, open(DATA / 'head_front_split.json', 'w'), indent=1); print(json.dumps(res, indent=1))
