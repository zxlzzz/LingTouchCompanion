"""Local wall thickness by the shrinking-ball method (largest inscribed ball touching each surface sample).
Thickness = ball diameter. Robust at L-corners where plain normal ray casting overestimates."""
import numpy as np
from scipy.spatial import cKDTree
import trimesh
from trimesh.ray.ray_pyembree import RayMeshIntersector


def sample_surface(V, F, spacing=0.25, seed=0):
    mesh = trimesh.Trimesh(V, F, process=False)
    n = int(mesh.area / spacing ** 2)
    pts, fid = trimesh.sample.sample_surface_even(mesh, n, radius=spacing * 0.5, seed=seed) if False else trimesh.sample.sample_surface(mesh, n, seed=seed)
    nrm = mesh.face_normals[fid]
    return mesh, np.asarray(pts), nrm, fid


def shrinking_ball(V, F, query_pts=None, query_nrm=None, spacing=0.25, iters=30, rmax=10.0):
    mesh, P, N, fid = sample_surface(V, F, spacing)
    tree = cKDTree(P)
    if query_pts is None:
        Q, QN = P, N
    else:
        Q, QN = query_pts, query_nrm
    # initial radius from inward ray hit distance / 2 (capped)
    ray = RayMeshIntersector(mesh)
    loc, idx_ray, _ = ray.intersects_location(Q - QN * 1e-4, -QN, multiple_hits=False)
    r = np.full(len(Q), rmax)
    d = np.linalg.norm(loc - Q[idx_ray], axis=1)
    r[idx_ray] = np.minimum(d / 2, rmax)
    r = np.maximum(r, 1e-3)
    for _ in range(iters):
        c = Q - QN * r[:, None]
        dist, j = tree.query(c)
        q = P[j]
        bad = dist < r - 1e-4
        if not bad.any():
            break
        pq = Q[bad] - q[bad]
        denom = 2 * np.einsum('ij,ij->i', -QN[bad], -pq) if False else 2 * np.einsum('ij,ij->i', QN[bad], pq)
        rn = np.einsum('ij,ij->i', pq, pq) / np.where(np.abs(denom) < 1e-9, 1e-9, denom)
        rn = np.clip(rn, 1e-3, r[bad])
        # avoid collapsing onto the sample itself
        same = np.einsum('ij,ij->i', pq, pq) < (spacing * 0.6) ** 2
        rn = np.where(same, r[bad], rn)
        r[bad] = rn
    return Q, QN, 2 * r
