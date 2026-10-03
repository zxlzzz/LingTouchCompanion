"""Step 9: the real CS30 housing profile at the hook positions (x = +-30, +-27, +-33): how the rear-bottom edge
looks where the 0.8 mm hooks sit (rounded edge would reduce real engagement)."""
import json, numpy as np
from common import DATA, IMG, section_segments
from render import section_image
a = np.load(DATA / 'cs30_housing_mesh.npz'); V, F = a['v'], a['f']
res = {}
layers = []
for xs, rgb in [(30.03, (220, 30, 30)), (27.03, (30, 120, 220)), (32.97, (30, 160, 60)), (-29.97, (150, 0, 200))]:
    s = section_segments(V, F, 0, xs)
    yz = s[:, :, [2, 1]]   # horizontal = Z_s (back -25 ... front 0), vertical = Y_s (bottom -12.5)
    layers.append((yz, rgb, f'X_s={xs}'))
    P = yz.reshape(-1, 2)
    # outermost profile near the rear-bottom corner: for h = 0..2 (Y_s=-12.5..-10.5) the rearmost Z_s, and for t=0..2 the lowest Y_s
    prof = {}
    for hh in [0.0, 0.2, 0.4, 0.6, 0.8, 1.0, 1.5, 2.0]:
        m = np.abs(P[:, 1] - (-12.5 + hh)) < 0.06
        prof[f'h={hh}'] = round(float(P[m, 0].min() + 25), 3) if m.any() else None   # t of rearmost point at that height
    res[f'X_s={xs}'] = {'rear_face_t_at_height_h (t=0 means at the 25 mm envelope back)': prof,
                        'bbox_Zs_Ys': [P.min(0).round(3).tolist(), P.max(0).round(3).tolist()]}
section_image(layers, IMG / 'stp_housing_section_at_hooks.png', 'Z_s (back=-25, front=0)', 'Y_s (bottom=-12.5)',
              'CS30 housing (customer STEP) sections at the hook x positions', extent=[[-26, -13.5], [1, 18]], grid=1)
section_image(layers, IMG / 'stp_housing_section_at_hooks_zoom.png', 'Z_s', 'Y_s', 'zoom: rear-bottom corner',
              extent=[[-25.5, -13], [-21, -9]], grid=0.5)
json.dump(res, open(DATA / 'hook_profile.json', 'w'), indent=1)
print(json.dumps(res, indent=1))
