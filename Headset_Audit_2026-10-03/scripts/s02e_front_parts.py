"""Step 2e: front view of the CS30 internals/windows (customer STEP) to identify optical openings."""
import sys, numpy as np
from common import DATA, IMG
from render import render
a = np.load(sys.argv[1]); V = a['v']; F = a['f']; P = a['part']
rng = np.random.default_rng(3)
meshes = []
info = []
for k in np.unique(P):
    ff = F[P == k]; vv = V[np.unique(ff)]
    lo, hi = vv.min(0), vv.max(0)
    if hi[2] > 0.5:          # FOV cones / frusta in front of the camera: skip
        continue
    if (hi - lo)[0] > 89:    # housing: skip, to see what sits behind the front glass
        continue
    if hi[2] < -6:           # deep internals: skip
        continue
    c = rng.random(3) * 170 + 60
    meshes.append((V, ff, c))
    info.append((k, lo.round(2).tolist(), hi.round(2).tolist()))
for i in info: print(i)
render(meshes, ((0, 0, 1), (0, 1, 0)), IMG / 'stp_front_parts_noHousing.png', size=1100,
       title='CS30_customer.stp, front view (+Z), housing & FOV cones hidden; STEP coords',
       marks=[((-22, 0, 0), 'RGB X-22', (200, 0, 0)), ((7, 0, 0), 'X7', (200, 0, 0)), ((22, 0, 0), 'RX X22', (200, 0, 0)), ((-6, 0, 0), 'X-6 ?', (200, 0, 0))])
