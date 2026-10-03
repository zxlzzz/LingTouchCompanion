"""Step 5: planar sections of the front part (shell, original BTTF, camera envelope, head)."""
import numpy as np
from common import read_3mf, FRONT_3MF, DATA, IMG, section_segments
from render import section_image
objs = read_3mf(FRONT_3MF)
shell = objs['Front_Compact_Review_shell']; cam = objs['Front_Compact_Review_occupant_reference_do_not_print']
head = objs['Head_reference_do_not_print']
b = np.load(DATA / 'bttf_normal_wearing.npz'); bttf = (b['v'], b['f'])
AX = {'X': 0, 'Y': 1, 'Z': 2}
def cut(name, axis, value, extent=None):
    k = AX[axis]; other = [i for i in range(3) if i != k]
    layers = []
    for (V, F), rgb, label in [(bttf, (190, 190, 190), 'original BTTF'), (head, (90, 90, 90), 'head'),
                               (cam, (235, 140, 30), 'camera 89.94x30x25'), (shell, (20, 120, 140), 'delivered shell')]:
        s = section_segments(V, F, k, value)
        layers.append((s[:, :, other] if len(s) else np.zeros((0, 2, 2)), rgb, label))
    lab = 'XYZ'
    section_image(layers, IMG / f'section_front_{name}.png', lab[other[0]], lab[other[1]],
                  f'front part, section {axis}={value}', extent=extent, grid=5)
EXT_YZ = [[-40, -5], [40, 65]]
for x in [0.37, -22.03, 7.03, 14.63, 21.97, 30.13, -30.13, 40.13, 44.63, 45.83, 46.73, 47.83, 52.13, 60.13, 64.63]:
    cut(f'X{x:+.2f}', 'X', x, EXT_YZ)
for z in [20.13, 25.13, 30.13, 40.13, 50.13, 54.63, 56.13]:
    cut(f'Z{z:.2f}', 'Z', z, [[-75, -40], [75, 60]])
for y in [-25.13, -15.13, -5.13, 1.13, 10.13]:
    cut(f'Y{y:+.2f}', 'Y', y, [[-75, -5], [75, 62]])
print('ok')
