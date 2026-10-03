"""Step 3: standard views of both delivered parts (shell alone, and shell + occupant + head)."""
import numpy as np
from common import read_3mf, FRONT_3MF, REAR_3MF, IMG
from render import render, VIEWS
SHELL = (40, 150, 165); OCC = (235, 150, 50); HEAD = (205, 205, 205)

def crop_head(V, F, lo, hi):
    keep = np.all((V[F] >= lo) & (V[F] <= hi), axis=(1, 2))
    return F[keep]

for tag, path in [('front', FRONT_3MF), ('rear', REAR_3MF)]:
    objs = read_3mf(path)
    shell = [v for k, v in objs.items() if k.endswith('_shell')][0]
    occ = [v for k, v in objs.items() if 'occupant' in k][0]
    head = objs['Head_reference_do_not_print']
    for view in VIEWS:
        render([(shell[0], shell[1], SHELL)], view, IMG / f'{tag}_shell_{view}.png', title=f'{tag} shell only - {view}')
    lo = shell[0].min(0) - 25; hi = shell[0].max(0) + 25
    hf = crop_head(head[0], head[1], lo, hi)
    for view in ['front', 'left', 'top', 'iso_front_left', 'iso_back_right', 'bottom']:
        render([(shell[0], shell[1], SHELL), (occ[0], occ[1], OCC), (head[0], hf, HEAD)], view,
               IMG / f'{tag}_assembly_{view}.png', bounds=np.vstack([shell[0].min(0), shell[0].max(0)]),
               title=f'{tag} shell + occupant + head (cropped) - {view}')
    for view in ['front', 'iso_front_left', 'iso_back_right', 'top', 'bottom', 'back']:
        render([(shell[0], shell[1], SHELL), (occ[0], occ[1], OCC)], view, IMG / f'{tag}_with_occupant_{view}.png',
               title=f'{tag} shell + occupant - {view}')
print('done')
