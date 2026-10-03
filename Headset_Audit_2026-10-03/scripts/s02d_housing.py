"""Step 2d: the CS30 housing part in CS30_customer.stp: circles (holes) on its faces, and views."""
import json, numpy as np
from s02_stp_probe import load, children, tessellate, bbox
from common import RAW, DATA, IMG
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopoDS import TopoDS
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.GeomAbs import GeomAbs_Circle
from render import render
s = load(RAW / 'CS30_customer.stp')
parts = [c for top in children(s) for c in children(top)]
best = None
for c in parts:
    try:
        V, F = tessellate(c, 0.05)
    except Exception:
        continue
    ext = V.max(0) - V.min(0)
    if abs(ext[0] - 89.94) < 0.1 and abs(ext[1] - 30) < 0.1 and abs(ext[2] - 25) < 0.1:
        best = (c, V, F)
c, V, F = best
print('housing mesh bounds', V.min(0).round(4), V.max(0).round(4))
circ = set()
e = TopExp_Explorer(c, TopAbs_EDGE)
while e.More():
    a = BRepAdaptor_Curve(TopoDS.Edge_s(e.Current()))
    if a.GetType() == GeomAbs_Circle:
        q = a.Circle(); p = q.Location(); n = q.Axis().Direction()
        circ.add(tuple(round(x, 4) for x in [p.X(), p.Y(), p.Z(), q.Radius(), n.X(), n.Y(), n.Z()]))
    e.Next()
circ = sorted(circ)
front = [x for x in circ if abs(abs(x[6]) - 1) < 1e-3 and x[2] > -0.6]
print('circles with axis Z on the front face region (Z>-0.6):')
for x in front: print(' ', x)
side = [x for x in circ if abs(abs(x[5]) - 1) < 1e-3 and x[3] > 0.5]
print('circles with axis Y (top/bottom faces), r>0.5:')
for x in side: print(' ', x)
np.savez_compressed(DATA / 'cs30_housing_mesh.npz', v=V, f=F)
json.dump({'housing_bounds': [V.min(0).tolist(), V.max(0).tolist()], 'front_circles': front, 'y_axis_circles': side}, open(DATA / 'cs30_housing_circles.json', 'w'), indent=1)
col = (90, 90, 110)
for vname, view in [('front', ((0, 0, 1), (0, 1, 0))), ('plusY', ((0, 1, 0), (0, 0, 1))), ('minusY', ((0, -1, 0), (0, 0, 1))), ('iso', ((0.5, 0.6, 1), (0, 1, 0)))]:
    render([(V, F, col)], view, IMG / f'stp_housing_{vname}.png', size=900, title=f'CS30_customer.stp housing, STEP coords, view {vname}')
