"""Step 6: local wall thickness of the delivered front shell; split by original-BTTF surface vs new surface."""
import json, numpy as np
from scipy.spatial import cKDTree
import trimesh
from common import read_3mf, FRONT_3MF, DATA, IMG
from thickness import shrinking_ball, sample_surface
from render import render
shell = read_3mf(FRONT_3MF)['Front_Compact_Review_shell']
b = np.load(DATA / 'bttf_normal_wearing.npz')
bt = trimesh.Trimesh(b['v'], b['f'], process=False)
mesh, P, N, fid = sample_surface(*shell, spacing=0.3, seed=1)
Q, QN, t = shrinking_ball(*shell, query_pts=P, query_nrm=N, spacing=0.2)
# Is this sample point on the original BTTF surface (unchanged original skin)?
_, dist, _ = trimesh.proximity.closest_point(bt, Q) if len(Q) < 0 else (None, None, None)
from scipy.spatial import cKDTree
bsamp, _ = trimesh.sample.sample_surface(bt, 3_000_000, seed=2)
dist = cKDTree(bsamp).query(Q)[0]
on_orig = dist < 0.15
# Is the point inside the original BTTF solid (=> material at that spot is original)?
inside_orig = bt.contains(Q - QN * 0.05)
np.savez_compressed('/tmp/claude-0/-home-user-LingTouchCompanion/a3d04089-c5dd-5567-a32c-b263c145e9d4/scratchpad/front_thickness.npz', Q=Q, QN=QN, t=t, on_orig=on_orig, inside_orig=inside_orig)
new = ~on_orig & ~inside_orig
res = {'samples': int(len(Q)), 'new_surface_samples': int(new.sum())}
for nm, m in [('all', np.ones(len(Q), bool)), ('new_surface', new), ('original_surface', on_orig)]:
    tt = t[m]
    res[nm] = {'p50': float(np.percentile(tt, 50)), 'p95': float(np.percentile(tt, 95)), 'p99': float(np.percentile(tt, 99)), 'max': float(tt.max()),
               'count_over_3.05': int((tt > 3.05).sum()), 'area_over_3.05_mm2_approx': float((tt > 3.05).sum() * mesh.area / len(Q))}
# cluster the new-surface samples thicker than 3.05 mm
over = new & (t > 3.05)
pts = Q[over]
clusters = []
if len(pts):
    tr = cKDTree(pts); lab = -np.ones(len(pts), int); k = 0
    for i in range(len(pts)):
        if lab[i] >= 0: continue
        stack = [i]; lab[i] = k
        while stack:
            j = stack.pop()
            for n in tr.query_ball_point(pts[j], 1.0):
                if lab[n] < 0: lab[n] = k; stack.append(n)
        k += 1
    for c in range(k):
        m = lab == c; tt = t[over][m]
        if m.sum() < 5: continue
        clusters.append({'n': int(m.sum()), 'max_mm': float(tt.max()), 'at_max_xyz': pts[m][tt.argmax()].round(2).tolist(),
                         'bbox_min': pts[m].min(0).round(1).tolist(), 'bbox_max': pts[m].max(0).round(1).tolist()})
clusters.sort(key=lambda c: -c['n'])
res['new_surface_clusters_over_3.05'] = clusters[:40]
json.dump(res, open(DATA / 'front_thickness.json', 'w'), indent=1)
print(json.dumps({k: v for k, v in res.items() if k != 'new_surface_clusters_over_3.05'}, indent=1))
for c in clusters[:25]: print(c)
