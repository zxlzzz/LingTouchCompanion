"""Shared helpers for the independent audit (own code; does not import ChatGPT scripts)."""
from pathlib import Path
import zipfile, re
import xml.etree.ElementTree as ET
import numpy as np

AUDIT = Path(__file__).resolve().parents[1]
REPO = AUDIT.parent
FRONT_3MF = REPO / 'Headset_CompactFront_Review_2026-10-02/Front_Compact_Review_Wearing.3mf'
REAR_3MF = REPO / 'Headset_Carbon6K_FlatBase_Review_2026-10-02/Rear_Carbon6K_FlatBase_Review_Wearing.3mf'
RAW = REPO / 'Headset_Repro/raw'
DATA = AUDIT / 'data'
IMG = AUDIT / 'images'


def read_3mf(path):
    """Return {object name: (V, F)} parsed directly from the 3MF XML (build transforms applied)."""
    with zipfile.ZipFile(path) as z:
        name = [n for n in z.namelist() if n.lower().endswith('.model')][0]
        root = ET.fromstring(z.read(name))
    ns = {'m': root.tag[1:root.tag.index('}')]}
    objs = {}
    for ob in root.iter('{%s}object' % ns['m']):
        vs = ob.find('.//m:vertices', ns)
        ts = ob.find('.//m:triangles', ns)
        if vs is None:
            continue
        V = np.array([[float(v.get('x')), float(v.get('y')), float(v.get('z'))] for v in vs], float)
        F = np.array([[int(t.get('v1')), int(t.get('v2')), int(t.get('v3'))] for t in ts], np.int64)
        objs[ob.get('id')] = (ob.get('name'), V, F)
    out = {}
    for it in root.iter('{%s}item' % ns['m']):
        nm, V, F = objs[it.get('objectid')]
        tr = it.get('transform')
        if tr:
            m = np.array([float(x) for x in tr.split()]).reshape(4, 3)
            V = V @ m[:3] + m[3]
        out[nm] = (V, F)
    return out


def volume(V, F):
    t = V[F]
    return float(np.einsum('ij,ij->i', t[:, 0], np.cross(t[:, 1], t[:, 2])).sum() / 6)


def edge_check(F):
    """Closed 2-manifold check: every undirected edge used exactly twice, opposite directions."""
    e = np.concatenate([F[:, [0, 1]], F[:, [1, 2]], F[:, [2, 0]]])
    key = np.sort(e, 1)
    u, inv, cnt = np.unique(key, axis=0, return_inverse=True, return_counts=True)
    directed = np.unique(e, axis=0)
    return {'edges': int(len(u)), 'non_two_edges': int((cnt != 2).sum()),
            'duplicate_directed_edges': int(len(e) - len(directed))}


def components(F, nv):
    """Connected components of faces via shared vertices (union-find)."""
    parent = np.arange(nv)
    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a
    for a, b, c in F:
        ra, rb, rc = find(a), find(b), find(c)
        parent[rb] = ra; parent[rc] = ra
    roots = np.array([find(i) for i in range(nv)])
    froot = roots[F[:, 0]]
    labels, finv = np.unique(froot, return_inverse=True)
    return finv, len(labels)


def section_segments(V, F, axis, value):
    """Intersect mesh with plane coord[axis]==value; return list of 3D segments (N,2,3)."""
    d = V[:, axis] - value
    t = V[F]; dd = d[F]
    s = np.sign(dd)
    mask = (s.min(1) < 0) & (s.max(1) > 0)
    segs = []
    for tri, di in zip(t[mask], dd[mask]):
        pts = []
        for i, j in [(0, 1), (1, 2), (2, 0)]:
            if (di[i] < 0) != (di[j] < 0):
                a = di[i] / (di[i] - di[j])
                pts.append(tri[i] + a * (tri[j] - tri[i]))
        if len(pts) == 2:
            segs.append(pts)
    return np.array(segs)
