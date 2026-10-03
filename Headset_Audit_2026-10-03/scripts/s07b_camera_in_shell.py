"""Step 7b: place the real CS30 (customer STEP, upright: tripod face down) in the delivered shell and render."""
import sys, numpy as np
from common import read_3mf, FRONT_3MF, IMG, DATA
from camframe import to_wear, step_to_local, HT
from render import render
a = np.load(sys.argv[1]); V = a['v']; F = a['f']; P = a['part']
L = step_to_local(V)
W = to_wear(L[:, 0], L[:, 1], L[:, 2])
shell = read_3mf(FRONT_3MF)['Front_Compact_Review_shell']
HIDE_HOUSING = len(sys.argv) > 2
SUF = '_nohousing' if HIDE_HOUSING else ''
keep_parts = []
cols = {0: (40, 80, 230), 1: (220, 30, 30), 2: (160, 40, 200), 3: (240, 200, 0)}
meshes = [(shell[0], shell[1], (40, 150, 165))]
for k in np.unique(P):
    ff = F[P == k]; vv = V[np.unique(ff)]
    if vv[:, 2].max() > 0.5: continue            # FOV cones in the STEP: skip
    if HIDE_HOUSING and (vv.max(0) - vv.min(0))[0] > 89: continue
    meshes.append((W, ff, cols.get(int(k), (70, 70, 80))))
# markers: lens centres as modelled (h=15) and actual (h=12.5)
marks = []
for nm, x in [('RGB', -22.025), ('TX', 6.975), ('RX', 21.975)]:
    marks.append((to_wear(x, 15, 25.6), f'{nm} h15 (model)', (255, 120, 0)))
    marks.append((to_wear(x, 12.5, 25.6), f'{nm} lens (STEP)', (255, 255, 255)))
bounds = np.array([[-45, -35, 10], [45, -15, 50]])
d = HT  # look against the optical axis
render(meshes, ((float(d[0]), float(d[1]), float(d[2])), (0, -0.342, 0.94)), IMG / f'front_real_camera_along_axis{SUF}.png', size=1300,
       bounds=bounds, marks=marks, title='Real CS30 (STEP, upright) in delivered shell, looking along the optical axis. blue=RGB ring, purple=TX window, red=RX window, yellow=X-6 part; orange dot = hole centre as modelled')
render(meshes, 'front', IMG / f'front_real_camera_front{SUF}.png', size=1300, bounds=np.array([[-75, -35, 0], [75, 0, 58]]), title='Real CS30 (STEP, upright) in delivered shell, front view (-Y)')
render(meshes, 'bottom', IMG / f'front_real_camera_bottom{SUF}.png', size=1300, bounds=np.array([[-75, -35, 0], [75, 20, 58]]), title='Real CS30 (STEP) in delivered shell, view from below')
render(meshes, 'iso_front_right_low', IMG / f'front_real_camera_iso_low{SUF}.png', size=1300, bounds=np.array([[-75, -35, 0], [75, 20, 58]]), title='Real CS30 (STEP) in delivered shell, low oblique')
