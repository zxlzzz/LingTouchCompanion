"""Distance / inside tests against the (open-necked) head mesh, memory-light:
KD-tree on dense head surface samples for all points, exact point-triangle refinement for the closest ones."""
import numpy as np, trimesh
from scipy.spatial import cKDTree
from trimesh.ray.ray_pyembree import RayMeshIntersector

class Head:
    def __init__(self, HV, HF, crop_lo=None, crop_hi=None, spacing=0.15):
        self.full = trimesh.Trimesh(HV, HF, process=False)
        self.ray = RayMeshIntersector(self.full)
        if crop_lo is not None:
            c = HV[HF].mean(1); k = np.all((c > crop_lo) & (c < crop_hi), 1)
            self.mesh = trimesh.Trimesh(HV, HF[k], process=False)
        else:
            self.mesh = self.full
        n = int(self.mesh.area / spacing ** 2)
        P, fid = trimesh.sample.sample_surface(self.mesh, n, seed=7)
        self.P = np.vstack([P, self.mesh.vertices]); self.tree = cKDTree(self.P)
    def inside(self, P):
        res = []
        for d in [(0, 0, 1.0), (0.3, -0.2, 0.93)]:
            d = np.array(d) / np.linalg.norm(d)
            _, idx, _ = self.ray.intersects_location(P, np.tile(d, (len(P), 1)), multiple_hits=True)
            res.append(np.bincount(idx, minlength=len(P)) % 2 == 1)
        return res[0] & res[1]
    def dist(self, P, refine=3000):
        d, _ = self.tree.query(P)
        k = np.argsort(d)[:refine]
        cp, de, _ = trimesh.proximity.closest_point(self.mesh, P[k])
        d = d.copy(); d[k] = de
        return d

def report(head, P, inside=True):
    d = head.dist(P)
    out = {'samples': int(len(P)), 'min_distance_mm': float(d.min()), 'at_xyz': P[d.argmin()].round(3).tolist()}
    if inside:
        ins = head.inside(P)
        out['samples_inside_head'] = int(ins.sum())
        if ins.any():
            # penetration depth: distance to surface of inside points (refine the deepest)
            dd = head.tree.query(P[ins])[0]
            k = np.argsort(-dd)[:2000]
            cp, de, _ = trimesh.proximity.closest_point(head.mesh, P[ins][k])
            out['max_penetration_mm'] = float(de.max()); out['deepest_at_xyz'] = P[ins][k][de.argmax()].round(3).tolist()
            q = P[ins]; out['inside_bbox'] = [q.min(0).round(2).tolist(), q.max(0).round(2).tolist()]
            out['_inside_mask'] = ins
    return out
