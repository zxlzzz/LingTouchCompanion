"""Step 13: local wall thickness of the delivered rear shell (shrinking ball)."""
import json, numpy as np
from scipy.spatial import cKDTree
from common import read_3mf, REAR_3MF, DATA
from thickness import shrinking_ball, sample_surface
SV, SF = [v for k, v in read_3mf(REAR_3MF).items() if k.endswith('_shell')][0]
mesh, P, N, fid = sample_surface(SV, SF, spacing=0.2, seed=1)
Q, QN, t = shrinking_ball(SV, SF, query_pts=P, query_nrm=N, spacing=0.15)
np.savez_compressed('/tmp/claude-0/-home-user-LingTouchCompanion/a3d04089-c5dd-5567-a32c-b263c145e9d4/scratchpad/rear_thickness.npz', Q=Q, QN=QN, t=t)
res = {'samples': int(len(Q)), 'p50': float(np.percentile(t, 50)), 'p95': float(np.percentile(t, 95)), 'p99': float(np.percentile(t, 99)), 'max': float(t.max())}
over = t > 3.05; pts = Q[over]; cl = []
if len(pts):
    tr = cKDTree(pts); lab = -np.ones(len(pts), int); k = 0
    for i in range(len(pts)):
        if lab[i] >= 0: continue
        st = [i]; lab[i] = k
        while st:
            j = st.pop()
            for n in tr.query_ball_point(pts[j], 1.0):
                if lab[n] < 0: lab[n] = k; st.append(n)
        k += 1
    for c in range(k):
        m = lab == c
        if m.sum() < 5: continue
        cl.append({'n': int(m.sum()), 'max_mm': float(t[over][m].max()), 'at': pts[m][t[over][m].argmax()].round(2).tolist(), 'bbox': [pts[m].min(0).round(1).tolist(), pts[m].max(0).round(1).tolist()]})
cl.sort(key=lambda c: -c['max_mm']); res['clusters_over_3.05'] = cl[:20]
json.dump(res, open(DATA / 'rear_thickness.json', 'w'), indent=1); print(json.dumps(res, indent=1))
