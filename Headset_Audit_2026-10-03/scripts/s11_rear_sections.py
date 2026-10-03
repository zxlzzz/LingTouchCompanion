"""Step 11: rear part sections (shell, battery, head)."""
import numpy as np
from common import read_3mf, REAR_3MF, IMG, section_segments
from render import section_image
objs = read_3mf(REAR_3MF)
shell = [v for k, v in objs.items() if k.endswith('_shell')][0]
bat = [v for k, v in objs.items() if 'occupant' in k][0]
head = objs['Head_reference_do_not_print']
AX = {'X': 0, 'Y': 1, 'Z': 2}
def cut(axis, value, extent, grid=2):
    k = AX[axis]; other = [i for i in range(3) if i != k]
    layers = []
    for (V, F), rgb, label in [(head, (90, 90, 90), 'head'), (bat, (235, 140, 30), 'battery 22.8x90.4'), (shell, (20, 120, 140), 'delivered rear shell')]:
        s = section_segments(V, F, k, value)
        layers.append((s[:, :, other] if len(s) else np.zeros((0, 2, 2)), rgb, label))
    section_image(layers, IMG / f'section_rear_{axis}{value:+.2f}.png', 'XYZ'[other[0]], 'XYZ'[other[1]], f'rear part, section {axis}={value}', extent=extent, grid=grid)
YZ = [[190, 22], [235, 60]]
for x in [0.37, 10.13, 18.47, 29.13, -29.13, 40.13, 45.13, -45.13, 46.83]:
    cut('X', x, YZ)
for z in [26.13, 33.13, 39.23, 45.23, 52.13, 55.13]:
    cut('Z', z, [[-50, 190], [50, 235]], grid=5)
for y in [199.83, 204.13, 217.13, 228.13, 229.33]:
    cut('Y', y, [[-50, 22], [50, 60]], grid=2)
print('ok')
