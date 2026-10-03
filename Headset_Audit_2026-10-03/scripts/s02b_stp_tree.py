"""Step 2b: list the STEP assembly tree (shape type, face count, bounds) for orientation."""
import sys
from s02_stp_probe import load, bbox
from common import RAW
from OCP.TopoDS import TopoDS_Iterator
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE

def walk(sh, d=0):
    it = TopoDS_Iterator(sh)
    while it.More():
        c = it.Value(); b = bbox(c)
        nf = 0; ex = TopExp_Explorer(c, TopAbs_FACE)
        while ex.More(): nf += 1; ex.Next()
        print('  ' * d, c.ShapeType().name, nf, [round(x, 2) for x in b], [round(b[3]-b[0], 2), round(b[4]-b[1], 2), round(b[5]-b[2], 2)])
        if d < 3 and c.ShapeType().name == 'TopAbs_COMPOUND': walk(c, d + 1)
        it.Next()
walk(load(RAW / sys.argv[1]))
