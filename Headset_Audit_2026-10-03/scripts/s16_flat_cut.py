"""Step 16: original BTTF faces still present in the delivered shell inside |X|<=45.3, Y -50..30, above Z=24.34."""
import json, numpy as np, trimesh
from scipy.spatial import cKDTree
from common import read_3mf, FRONT_3MF, DATA
SV, SF = read_3mf(FRONT_3MF)['Front_Compact_Review_shell']
b = np.load(DATA / 'bttf_normal_wearing.npz'); bt = trimesh.Trimesh(b['v'], b['f'], process=False)
P, _ = trimesh.sample.sample_surface(bt, 3000000, seed=11)
reg = (np.abs(P[:, 0]) <= 45.3) & (P[:, 1] > -50) & (P[:, 1] < 30) & (P[:, 2] > 24.35)
Q = P[reg]
sm = trimesh.Trimesh(SV, SF, process=False)
S_, _ = trimesh.sample.sample_surface(sm, 4000000, seed=12)
d = cKDTree(S_).query(Q)[0]
on_shell = d < 0.05
res = {'bttf_surface_samples_in_region': int(len(Q)), 'still_on_delivered_surface': int(on_shell.sum())}
if on_shell.any():
    q = Q[on_shell]; res['retained_bbox'] = [q.min(0).round(3).tolist(), q.max(0).round(3).tolist()]
    res['retained_z_values_top'] = sorted(set(np.round(q[:, 2], 2).tolist()))[-10:]
# exclude the top face Z>55.13 (shared plane with the new top plate) and see what is left
oth = on_shell & (Q[:, 2] < 55.1)
res['retained_below_Z55.1'] = int(oth.sum())
if oth.any():
    q = Q[oth]; res['retained_below_Z55.1_bbox'] = [q.min(0).round(3).tolist(), q.max(0).round(3).tolist()]
# also: highest shell point of ORIGINAL-like vertical wall in the band |X|<=45.3, Y 0..13 (the old front wall), by rays down
json.dump(res, open(DATA / 'flat_cut.json', 'w'), indent=1); print(json.dumps(res, indent=1))
q = Q[oth]
res['retained_below_Z55.1_abs_x_hist'] = {f'{a}-{b}': int(((np.abs(q[:, 0]) >= a) & (np.abs(q[:, 0]) < b)).sum()) for a, b in [(0, 40), (40, 45), (45, 45.25), (45.25, 45.31)]}
inner = q[np.abs(q[:, 0]) < 45.25]
res['retained_inside_|X|<45.25'] = int(len(inner))
if len(inner): res['inside_points_sample'] = inner[:10].round(2).tolist()
json.dump(res, open(DATA / 'flat_cut.json', 'w'), indent=1); print(res['retained_below_Z55.1_abs_x_hist'], res['retained_inside_|X|<45.25'], res.get('inside_points_sample'))
