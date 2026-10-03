"""Own orthographic renderer (no GPU here): Embree ray casting per pixel, flat shading, Pillow output.

Views are named by where the camera looks FROM, in wearing coordinates
(X left/right, Y posterior, Z up; the face front is -Y).
"""
import numpy as np
from PIL import Image, ImageDraw, ImageFont

VIEWS = {
    # name: (direction from object to camera, up vector)
    'front': ((0, -1, 0), (0, 0, 1)),
    'back': ((0, 1, 0), (0, 0, 1)),
    'left': ((-1, 0, 0), (0, 0, 1)),     # camera at -X
    'right': ((1, 0, 0), (0, 0, 1)),
    'top': ((0, 0, 1), (0, -1, 0)),      # front (-Y) up in the image
    'bottom': ((0, 0, -1), (0, -1, 0)),
    'iso_front_left': ((-1, -1.3, 0.8), (0, 0, 1)),
    'iso_front_right_low': ((1, -1.3, -0.6), (0, 0, 1)),
    'iso_back_right': ((1, 1.2, 0.9), (0, 0, 1)),
    'iso_back_left_low': ((-1, 1.2, -0.5), (0, 0, 1)),
}


def basis(view):
    d, up = VIEWS[view] if isinstance(view, str) else view
    d = np.array(d, float); d /= np.linalg.norm(d)
    up = np.array(up, float)
    r = np.cross(up, d); r /= np.linalg.norm(r)
    u = np.cross(d, r)
    return r, u, d


def render(meshes, view, out, size=1100, title=None, bounds=None, marks=(), font_size=18, return_ids=False):
    """Ray-cast orthographic render (exact visibility, Embree via trimesh).
    meshes: list of (V, F, rgb). bounds: optional 3D points defining the framed region.
    marks: list of (xyz, label, rgb) labelled dots. Back faces are drawn darker."""
    import trimesh
    from trimesh.ray.ray_pyembree import RayMeshIntersector
    r, u, d = basis(view)
    Vs, Fs, C, M, n0 = [], [], [], [], 0
    for k, (V, F, rgb) in enumerate(meshes):
        Vs.append(V); Fs.append(F + n0); n0 += len(V)
        C.append(np.tile(np.array(rgb, float), (len(F), 1))); M.append(np.full(len(F), k))
    V = np.concatenate(Vs); F = np.concatenate(Fs); C = np.concatenate(C); M = np.concatenate(M)
    allV = V[np.unique(F)] if bounds is None else np.asarray(bounds, float)
    p2 = np.stack([allV @ r, allV @ u], 1)
    lo, hi = p2.min(0), p2.max(0)
    span = (hi - lo).max() * 1.08
    c = (lo + hi) / 2
    scale = size / span
    depth0 = (V @ d).max() + 10
    ii, jj = np.meshgrid(np.arange(size), np.arange(size))
    a = (ii.ravel() + 0.5 - size / 2) / scale + c[0]
    b = (size / 2 - (jj.ravel() + 0.5)) / scale + c[1]
    origins = a[:, None] * r + b[:, None] * u + depth0 * d
    dirs = np.tile(-d, (len(origins), 1))
    mesh = trimesh.Trimesh(V, F, process=False)
    tri = RayMeshIntersector(mesh).intersects_first(origins, dirs)
    N = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    N /= np.maximum(np.linalg.norm(N, axis=1), 1e-12)[:, None]
    light = d * 0.6 + u * 0.5 + r * 0.25; light /= np.linalg.norm(light)
    img = np.full((size * size, 3), 255.0)
    hit = tri >= 0
    t = tri[hit]
    shade = np.abs(N[t] @ light) * 0.7 + 0.3
    front = (N[t] @ d) > 0
    shade = np.where(front, shade, shade * 0.5)
    img[hit] = C[t] * shade[:, None]
    ids = np.full(size * size, -1); ids[hit] = M[t]
    img = Image.fromarray(img.reshape(size, size, 3).clip(0, 255).astype(np.uint8))
    dr = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default(size=font_size)
    except TypeError:
        font = ImageFont.load_default()
    def to_px(P):
        q = np.stack([P @ r, P @ u], 1)
        return np.stack([(q[:, 0] - c[0]) * scale + size / 2, size / 2 - (q[:, 1] - c[1]) * scale], 1)
    for xyz, label, rgb in marks:
        p = to_px(np.array([xyz], float))[0]
        dr.ellipse([p[0] - 5, p[1] - 5, p[0] + 5, p[1] + 5], fill=rgb, outline=(0, 0, 0))
        dr.text((p[0] + 8, p[1] - 8), label, fill=rgb, font=font)
    bar = 10 * scale
    dr.line([(20, size - 30), (20 + bar, size - 30)], fill=(0, 0, 0), width=3)
    dr.text((20, size - 55), '10 mm', fill=(0, 0, 0), font=font)
    def axname(vec):
        k = int(np.argmax(np.abs(vec))); s = '+' if vec[k] > 0 else '-'
        return s + 'XYZ'[k]
    dr.text((size - 260, size - 55), f'right={axname(r)} up={axname(u)}', fill=(0, 0, 0), font=font)
    if title:
        dr.text((15, 10), title, fill=(0, 0, 0), font=font)
    img.save(out)
    if return_ids:
        return ids.reshape(size, size), 1 / scale
    return out


def section_image(polys, out, xlabel, ylabel, title, size=1000, extent=None, grid=5.0, notes=()):
    """polys: list of (segments (N,2,2), rgb, label). Draw 2D section segments with a mm grid."""
    allp = np.concatenate([s.reshape(-1, 2) for s, _, _ in polys if len(s)]) if extent is None else np.asarray(extent, float)
    lo, hi = allp.min(0), allp.max(0)
    span = (hi - lo).max() * 1.1; c = (lo + hi) / 2; sc = size / span
    def px(p):
        return ((p[..., 0] - c[0]) * sc + size / 2, size / 2 - (p[..., 1] - c[1]) * sc)
    img = Image.new('RGB', (size, size + 60), (255, 255, 255)); dr = ImageDraw.Draw(img)
    try:
        font = ImageFont.load_default(size=16)
    except TypeError:
        font = ImageFont.load_default()
    g0 = np.floor((c - span / 2) / grid) * grid
    for k in range(int(span / grid) + 3):
        for axis in (0, 1):
            v = g0[axis] + k * grid
            if axis == 0:
                x, _ = px(np.array([v, 0.0])); dr.line([(x, 0), (x, size)], fill=(232, 232, 232))
                if k % 2 == 0: dr.text((x + 2, size - 18), f'{v:g}', fill=(120, 120, 120), font=font)
            else:
                _, y = px(np.array([0.0, v])); dr.line([(0, y), (size, y)], fill=(232, 232, 232))
                if k % 2 == 0: dr.text((2, y - 16), f'{v:g}', fill=(120, 120, 120), font=font)
    ly = size + 5
    for li, (segs, rgb, label) in enumerate(polys):
        if len(segs):
            x, y = px(segs)
            for a in range(len(segs)):
                dr.line([(x[a, 0], y[a, 0]), (x[a, 1], y[a, 1])], fill=rgb, width=2)
        dr.text((10 + 230 * li, ly), label, fill=rgb, font=font)
    for xy, label, rgb in notes:
        x, y = px(np.array(xy, float))
        dr.ellipse([x - 4, y - 4, x + 4, y + 4], outline=rgb, width=2)
        dr.text((x + 6, y - 6), label, fill=rgb, font=font)
    dr.text((10, ly + 25), f'{title}   horizontal={xlabel}  vertical={ylabel}  grid={grid:g} mm', fill=(0, 0, 0), font=font)
    img.save(out)
    return out
