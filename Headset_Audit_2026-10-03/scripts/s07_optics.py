"""Step 7: lens openings vs the real lens positions (from the official STEP), by ray casting against the shell.
(a) aperture: share of each lens disk visible straight ahead; (b) field of view blocked;
(c) camera front face area exposed through the openings (straight-on and oblique views)."""
import json, math, numpy as np
import trimesh
from trimesh.ray.ray_pyembree import RayMeshIntersector
from common import read_3mf, FRONT_3MF, DATA
from camframe import to_wear, HX, HH, HT, STEP_XC
shell = read_3mf(FRONT_3MF)['Front_Compact_Review_shell']
mesh = trimesh.Trimesh(*shell, process=False); ray = RayMeshIntersector(mesh)

# Lens data measured from the STEP files (see optics_circles.json). x is housing-centred.
LENSES = {
    'RGB': dict(x=-22 - STEP_XC, d=9.95, t_front=25 - 1.13, fov=(112, 63), note='ring opening dia 9.95 (glass 8.8), front of glass Z=-1.13'),
    'TX': dict(x=7 - STEP_XC, rect=(2.79, 2.84), t_front=25 - 1.7, fov=(110, 90), note='diffuser top 2.79x2.84 at Z=-1.7'),
    'RX': dict(x=22 - STEP_XC, d=10.5, t_front=25 - 2.0, fov=(100, 75), note='lens front ring dia 10.5 at Z=-2.0/-2.05'),
}
def aperture_pts(L, step=0.1):
    if 'd' in L:
        r = L['d'] / 2; g = np.arange(-r, r + 1e-9, step); a, b = np.meshgrid(g, g); m = a ** 2 + b ** 2 <= r * r
    else:
        w, h = L['rect']; a, b = np.meshgrid(np.arange(-w / 2, w / 2 + 1e-9, step), np.arange(-h / 2, h / 2 + 1e-9, step)); m = np.ones_like(a, bool)
    return a[m], b[m]
def blocked(origins, dirs):
    hit = ray.intersects_any(origins, dirs)
    return hit
res = {}
for h_center, tag in [(15.0, 'as_modelled_h15'), (12.5, 'actual_upright_h12.5')]:
    out = {}
    for name, L in LENSES.items():
        a, b = aperture_pts(L)
        P = to_wear(L['x'] + a, h_center + b, L['t_front'])
        fwd = np.tile(HT, (len(P), 1))
        straight = blocked(P + fwd * 1e-3, fwd)
        # field of view: rectangular H x V, 2 deg grid, from aperture centre and from 60 points across the aperture
        H, V = L['fov']
        ax = np.radians(np.arange(-H / 2, H / 2 + 1e-9, 2.0)); av = np.radians(np.arange(-V / 2, V / 2 + 1e-9, 2.0))
        A, B = np.meshgrid(ax, av); A = A.ravel(); B = B.ravel()
        D = HT[None] + np.tan(A)[:, None] * HX[None] + np.tan(B)[:, None] * HH[None]
        D /= np.linalg.norm(D, axis=1)[:, None]
        c0 = to_wear(L['x'], h_center, L['t_front'])
        bc = blocked(np.tile(c0 + HT * 1e-3, (len(D), 1)), D)
        idx = np.random.default_rng(0).choice(len(P), min(60, len(P)), replace=False)
        Ob = np.repeat(P[idx] + HT * 1e-3, len(D), 0); Db = np.tile(D, (len(idx), 1))
        ba = blocked(Ob, Db).reshape(len(idx), len(D))
        worst = None
        if bc.any():
            k = np.argmax(np.abs(np.degrees(A)) * 0 + bc * (np.abs(np.degrees(B)) + 0.001))
            # report extremes of blocked directions
            worst = {'h_deg_range': [float(np.degrees(A[bc]).min()), float(np.degrees(A[bc]).max())],
                     'v_deg_range': [float(np.degrees(B[bc]).min()), float(np.degrees(B[bc]).max())]}
        out[name] = {'lens_centre_wearing_xyz': c0.round(3).tolist(),
                     'aperture_share_blocked_straight_ahead': float(straight.mean()),
                     'fov_dirs_blocked_from_centre_share': float(bc.mean()), 'fov_blocked_from_centre_extent_deg': worst,
                     'fov_rays_blocked_from_whole_aperture_share': float(ba.mean()),
                     'directions_blocked_for_any_aperture_point_share': float(ba.any(0).mean())}
    res[tag] = out
# (c) exposure of the camera front face (housing front plane t=25) through the openings
def exposed(view_dirs, step=0.1):
    g1 = np.arange(-44.97, 44.97, step); g2 = np.arange(0, 30, step)
    X, Hh = np.meshgrid(g1, g2); X = X.ravel(); Hh = Hh.ravel()
    P = to_wear(X, Hh, 25.0) + HT * 1e-3
    vis = np.zeros(len(P), bool)
    for d in view_dirs:
        d = np.asarray(d, float); d /= np.linalg.norm(d)
        vis |= ~ray.intersects_any(P, np.tile(d, (len(P), 1)))
    return X, Hh, vis
views = {'straight_on_optical_axis': [HT], 'straight_front_-Y': [np.array([0, -1, 0])],
         'cone_30deg': [HT + math.tan(math.radians(30)) * (math.cos(a) * HX + math.sin(a) * HH) for a in np.linspace(0, 2 * math.pi, 12, endpoint=False)] + [HT]}
exp = {}
for vn, vd in views.items():
    X, Hh, vis = exposed(vd)
    cell = 0.01
    lens_mask = np.zeros(len(X), bool)
    for hc_tag, hc in [('h12.5', 12.5)]:
        for L in LENSES.values():
            if 'd' in L: lens_mask |= (X - L['x']) ** 2 + (Hh - hc) ** 2 <= (L['d'] / 2) ** 2
            else: lens_mask |= (np.abs(X - L['x']) <= L['rect'][0] / 2) & (np.abs(Hh - hc) <= L['rect'][1] / 2)
    exp[vn] = {'exposed_front_face_mm2': float(vis.sum() * cell), 'of_which_lens_mm2': float((vis & lens_mask).sum() * cell),
               'non_lens_exposed_mm2': float((vis & ~lens_mask).sum() * cell), 'lens_area_total_mm2': float(lens_mask.sum() * cell),
               'lens_area_hidden_mm2': float((lens_mask & ~vis).sum() * cell),
               'exposed_x_range': [float(X[vis].min()), float(X[vis].max())] if vis.any() else None,
               'exposed_h_range': [float(Hh[vis].min()), float(Hh[vis].max())] if vis.any() else None}
    if vn == 'straight_on_optical_axis':
        np.savez_compressed(DATA / 'front_face_exposure_map.npz', x=X, h=Hh, vis=vis, lens=lens_mask)
res['front_face_exposure_lenses_at_h12.5'] = exp
res['lenses'] = {k: {kk: vv for kk, vv in v.items()} for k, v in LENSES.items()}
json.dump(res, open(DATA / 'optics_check.json', 'w'), indent=1)
print(json.dumps(res, indent=1))
