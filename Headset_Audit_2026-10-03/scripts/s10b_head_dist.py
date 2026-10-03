"""Step 10b: distances / overlaps to the head model. Arg: which check."""
import sys, json, time, numpy as np, trimesh
from common import read_3mf, FRONT_3MF, REAR_3MF, DATA
from headdist import Head, report
t0 = time.time()
which = sys.argv[1]
objs = read_3mf(FRONT_3MF)
HV, HF = objs['Head_reference_do_not_print']
def samples(V, F, n):
    P, _ = trimesh.sample.sample_surface(trimesh.Trimesh(V, F, process=False), n, seed=3); return np.vstack([P, V])
if which == 'camera':
    V, F = objs['Front_Compact_Review_occupant_reference_do_not_print']; P = samples(V, F, 100000)
elif which == 'new':
    a = np.load(DATA / 'front_new_material.npz'); P = samples(a['v'], a['f'], 300000)
elif which == 'shell':
    V, F = objs['Front_Compact_Review_shell']; P = samples(V, F, 400000)
elif which == 'rear':
    V, F = [v for k, v in read_3mf(REAR_3MF).items() if k.endswith('_shell')][0]; P = samples(V, F, 300000)
head = Head(HV, HF, crop_lo=P.min(0) - 10, crop_hi=P.max(0) + 10, spacing=0.2)
print('head ready', time.time() - t0, len(head.P), flush=True)
r = report(head, P)
ins = r.pop('_inside_mask', None)
if ins is not None: np.save(DATA / f'{which}_inside_head_pts.npy', P[ins])
if which == 'new':
    nose = (np.abs(P[:, 0]) < 30) & (P[:, 2] < 45) & (P[:, 1] < 30)
    r['nose_zone(|X|<30,Z<45,Y<30)'] = report(head, P[nose], inside=False)
r['seconds'] = time.time() - t0
json.dump(r, open(DATA / f'head_{which}.json', 'w'), indent=1); print(json.dumps(r, indent=1))
