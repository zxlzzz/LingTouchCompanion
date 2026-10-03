"""Step 18: rear pad (arc tray) head-facing surface: distance to the head over its whole area."""
import json, numpy as np, trimesh
from common import read_3mf, REAR_3MF, DATA
from headdist import Head
objs = read_3mf(REAR_3MF)
SV, SF = [v for k, v in objs.items() if k.endswith('_shell')][0]; HV, HF = objs['Head_reference_do_not_print']
m = trimesh.Trimesh(SV, SF, process=False)
P, fid = trimesh.sample.sample_surface(m, 400000, seed=4); N = m.face_normals[fid]
c = P.mean(0)
# head-facing: normal points toward the head (towards -Y and towards the head centre), within the pad footprint
face = (np.abs(P[:, 0]) <= 20.01) & (P[:, 1] < 200.5) & (N[:, 1] < -0.5)
Q = P[face]
head = Head(HV, HF, crop_lo=Q.min(0) - 10, crop_hi=Q.max(0) + 10, spacing=0.1)
d = head.dist(Q, refine=len(Q))
ins = head.inside(Q)
res = {'pad_face_samples': int(len(Q)), 'min_mm': float(d.min()), 'max_mm': float(d.max()), 'p5': float(np.percentile(d, 5)), 'p95': float(np.percentile(d, 95)),
       'inside_head': int(ins.sum()), 'at_max': Q[d.argmax()].round(2).tolist(), 'at_min': Q[d.argmin()].round(2).tolist(),
       'share_within_0_2mm': float(((d >= 0) & (d <= 2) & ~ins).mean()),
       'pad_bbox': [Q.min(0).round(2).tolist(), Q.max(0).round(2).tolist()]}
json.dump(res, open(DATA / 'rear_pad_head.json', 'w'), indent=1); print(json.dumps(res, indent=1))
