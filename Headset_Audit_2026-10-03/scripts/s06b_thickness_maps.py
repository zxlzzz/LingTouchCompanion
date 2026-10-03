"""Step 6b: thickness maps (sample points colored by local thickness), projected views."""
import sys, numpy as np
from PIL import Image, ImageDraw, ImageFont
from common import IMG
from render import basis
a = np.load(sys.argv[1]); Q, QN, t = a['Q'], a['QN'], a['t']
tag = sys.argv[2]
def color(v):
    # <1.2 purple, 1.2-1.8 blue, 1.8-2.6 green, 2.6-3.05 yellow, >3.05 red
    c = np.zeros((len(v), 3), np.uint8)
    for lo, hi, rgb in [(0, 1.2, (150, 0, 200)), (1.2, 1.8, (40, 90, 230)), (1.8, 2.6, (60, 170, 60)), (2.6, 3.05, (230, 190, 0)), (3.05, 99, (220, 20, 20))]:
        c[(v >= lo) & (v < hi)] = rgb
    return c
font = ImageFont.load_default(size=16)
for view in ['front', 'top', 'left', 'right', 'iso_front_left', 'iso_back_right', 'bottom', 'back']:
    r, u, d = basis(view)
    vis = (QN @ d) > 0.05
    P = Q[vis]; tt = t[vis]
    x, y = P @ r, P @ u; z = P @ d
    size = 1100
    lo = np.array([x.min(), y.min()]); hi = np.array([x.max(), y.max()]); span = (hi - lo).max() * 1.08; c = (lo + hi) / 2; sc = size / span
    px = ((x - c[0]) * sc + size / 2).astype(int); py = (size / 2 - (y - c[1]) * sc).astype(int)
    order = np.argsort(z)  # far first, near last
    img = np.full((size, size, 3), 255, np.uint8); zbuf = np.full((size, size), -1e9)
    col = color(tt)
    for k in order:
        X0, Y0 = px[k], py[k]
        img[max(Y0-1,0):Y0+2, max(X0-1,0):X0+2] = col[k]
    im = Image.fromarray(img); dr = ImageDraw.Draw(im)
    dr.text((10, 10), f'{tag}: local wall thickness (inscribed ball), view {view}', fill=(0, 0, 0), font=font)
    for i, (lab, rgb) in enumerate([('<1.2', (150, 0, 200)), ('1.2-1.8', (40, 90, 230)), ('1.8-2.6', (60, 170, 60)), ('2.6-3.05', (230, 190, 0)), ('>3.05 mm', (220, 20, 20))]):
        dr.rectangle([10 + 110 * i, size - 40, 30 + 110 * i, size - 20], fill=rgb); dr.text((35 + 110 * i, size - 40), lab, fill=(0, 0, 0), font=font)
    im.save(IMG / f'{tag}_thickness_{view}.png')
