"""Camera frame. Local (x, h, t): x across, h up from camera bottom, t forward from camera back.
Pivot / tilt values are the ones the brief states (rear-lower edge (2.60, 24.84), 20 deg down);
the exact pivot is taken from the delivered camera reference object corners."""
import math, numpy as np
from common import read_3mf, FRONT_3MF
C, S = math.cos(math.radians(20)), math.sin(math.radians(20))
_cam = read_3mf(FRONT_3MF)['Front_Compact_Review_occupant_reference_do_not_print'][0]
# rear-lower edge = vertex with max Y
PY, PZ = _cam[np.argmax(_cam[:, 1])][1:]
HX = np.array([1.0, 0, 0]); HH = np.array([0, -S, C]); HT = np.array([0, -C, -S])
O = np.array([0, PY, PZ])
def to_wear(x, h, t):
    x, h, t = np.broadcast_arrays(np.asarray(x, float), np.asarray(h, float), np.asarray(t, float))
    return O + x[..., None] * HX + h[..., None] * HH + t[..., None] * HT
# STEP (CS30_customer.stp) -> local: housing X centre, bottom (tripod face) Y=-12.5, back Z=-25
STEP_XC = (-44.9419 + 44.9919) / 2
def step_to_local(P, upright=True):
    P = np.asarray(P, float)
    if upright:
        return np.stack([P[..., 0] - STEP_XC, P[..., 1] + 12.5, P[..., 2] + 25], -1)
    return np.stack([-(P[..., 0] - STEP_XC), 17.5 - P[..., 1], P[..., 2] + 25], -1)
