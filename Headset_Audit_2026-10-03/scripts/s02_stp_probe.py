"""Step 2a: read the official CS30 STEP files with OCP; overall bounds and solids."""
import sys, json
from OCP.STEPControl import STEPControl_Reader
from OCP.IFSelect import IFSelect_RetDone
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_SOLID, TopAbs_FACE
from common import RAW

def load(path):
    r = STEPControl_Reader()
    assert r.ReadFile(str(path)) == IFSelect_RetDone
    r.TransferRoots()
    return r.OneShape()

def bbox(s):
    b = Bnd_Box(); BRepBndLib.Add_s(s, b, True)
    return b.Get()

if __name__ == '__main__':
    for fn in ['CS30_customer.stp', 'CS30_official.stp']:
        s = load(RAW / fn)
        print(fn, 'bbox', [round(x, 4) for x in bbox(s)])
        ex = TopExp_Explorer(s, TopAbs_SOLID); n = 0
        sols = []
        while ex.More():
            sols.append([round(x, 3) for x in bbox(ex.Current())]); n += 1; ex.Next()
        print(' solids', n)
        for b in sorted(sols, key=lambda b: -(b[3]-b[0])*(b[4]-b[1])*(b[5]-b[2]))[:40]:
            print('  ', b, 'size', [round(b[3]-b[0], 3), round(b[4]-b[1], 3), round(b[5]-b[2], 3)])


def tessellate(shape, defl=0.02):
    """Triangulate an OCP shape into numpy (V, F)."""
    import numpy as np
    from OCP.BRepMesh import BRepMesh_IncrementalMesh
    from OCP.BRep import BRep_Tool
    from OCP.TopLoc import TopLoc_Location
    from OCP.TopoDS import TopoDS
    from OCP.TopAbs import TopAbs_REVERSED
    BRepMesh_IncrementalMesh(shape, defl, False, 0.3, True)
    Vs, Fs, n = [], [], 0
    ex = TopExp_Explorer(shape, TopAbs_FACE)
    while ex.More():
        f = TopoDS.Face_s(ex.Current()); loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(f, loc)
        if tri is not None:
            tr = loc.Transformation()
            V = np.array([[p.X(), p.Y(), p.Z()] for p in (tri.Node(i).Transformed(tr) for i in range(1, tri.NbNodes() + 1))])
            F = np.array([tri.Triangle(i).Get() for i in range(1, tri.NbTriangles() + 1)]) - 1
            if f.Orientation() == TopAbs_REVERSED: F = F[:, ::-1]
            Vs.append(V); Fs.append(F + n); n += len(V)
        ex.Next()
    return np.concatenate(Vs), np.concatenate(Fs)


def children(shape):
    from OCP.TopoDS import TopoDS_Iterator
    it = TopoDS_Iterator(shape); out = []
    while it.More(): out.append(it.Value()); it.Next()
    return out
