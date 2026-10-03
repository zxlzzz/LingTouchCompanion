"""Step 2f: circles (axis along the optical axis) near each optical element, from both official STEP files."""
import json
from s02_stp_probe import load
from common import RAW, DATA
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_EDGE
from OCP.TopoDS import TopoDS
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.GeomAbs import GeomAbs_Circle
out = {}
for fn in ['CS30_official.stp', 'CS30_customer.stp']:
    s = load(RAW / fn); circ = set()
    e = TopExp_Explorer(s, TopAbs_EDGE)
    while e.More():
        a = BRepAdaptor_Curve(TopoDS.Edge_s(e.Current()))
        if a.GetType() == GeomAbs_Circle:
            q = a.Circle(); p = q.Location(); n = q.Axis().Direction()
            if abs(abs(n.Z()) - 1) < 1e-4:
                circ.add((round(p.X(), 3), round(p.Y(), 3), round(p.Z(), 3), round(q.Radius(), 4)))
        e.Next()
    res = {}
    for name, cx in [('RGB', -22), ('X-6', -6), ('TX', 7), ('RX', 22)]:
        sel = sorted([c for c in circ if abs(c[0] - cx) < 1.5 and abs(c[1]) < 1.5 and c[2] > -4], key=lambda c: (-c[2], c[3]))
        res[name] = sel
    out[fn] = res
    print(fn)
    for k, v in res.items():
        print(' ', k, v[:30])
json.dump(out, open(DATA / 'optics_circles.json', 'w'), indent=1)
