"""Step 19: the raised top strip (Z 55.18-57.14) on the arms: width in plan, by Y."""
import json, numpy as np, trimesh
from trimesh.ray.ray_pyembree import RayMeshIntersector
from common import read_3mf, FRONT_3MF, DATA
SV, SF = read_3mf(FRONT_3MF)['Front_Compact_Review_shell']
ray = RayMeshIntersector(trimesh.Trimesh(SV, SF, process=False))
res = {}
for side in [-1, 1]:
    rows = []
    for y in np.arange(10.13, 80, 5.0):
        xs = side * np.arange(55, 76, 0.02)
        O = np.stack([xs, np.full(len(xs), y), np.full(len(xs), 80.0)], 1)
        l, idx, _ = ray.intersects_location(O, np.tile([0, 0, -1.0], (len(O), 1)), multiple_hits=False)
        z = np.full(len(xs), np.nan); z[idx] = l[:, 2]
        hi = z > 57.1
        if hi.any():
            # width of the outermost raised run
            ax = np.abs(xs[hi]); rows.append({'y': round(float(y), 2), 'raised_|x|_from': round(float(ax.min()), 2), 'to': round(float(ax.max()), 2), 'width_mm': round(float(hi.sum() * 0.02), 2)})
        else:
            rows.append({'y': round(float(y), 2), 'raised': 'none', 'top_z_max': round(float(np.nanmax(z)), 2) if np.isfinite(z).any() else None})
    res['left' if side < 0 else 'right'] = rows
json.dump(res, open(DATA / 'arm_top_strip.json', 'w'), indent=1)
for k, v in res.items():
    print(k); [print('  ', r) for r in v]
