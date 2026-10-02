from pathlib import Path
import json
from OCP.STEPControl import STEPControl_Reader
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_SOLID,TopAbs_EDGE
from OCP.TopoDS import TopoDS
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.GeomAbs import GeomAbs_Circle
P=Path(__file__).resolve().parent
def bounds(s):
 b=Bnd_Box();BRepBndLib.AddOptimal_s(s,b,False,False)
 a,z=b.CornerMin(),b.CornerMax()
 return [a.X(),a.Y(),a.Z(),z.X(),z.Y(),z.Z()]
r=STEPControl_Reader();r.ReadFile(str(P/'inputs/CS30_customer.stp'));r.TransferRoots();shape=r.OneShape()
print('ALL BOUNDS',bounds(shape))
e=TopExp_Explorer(shape,TopAbs_SOLID);i=0;solids=[]
while e.More():
 s=e.Current();bb=bounds(s);circ=[];ex=TopExp_Explorer(s,TopAbs_EDGE)
 while ex.More():
  try:
   c=BRepAdaptor_Curve(TopoDS.Edge(ex.Current()))
   if c.GetType()==GeomAbs_Circle:
    cc=c.Circle();p=cc.Location();n=cc.Axis().Direction();circ.append([round(p.X(),6),round(p.Y(),6),round(p.Z(),6),round(cc.Radius(),6),round(n.X(),4),round(n.Y(),4),round(n.Z(),4)])
  except Exception:pass
  ex.Next()
 circ=sorted(set(tuple(a) for a in circ));solids.append({'index':i,'bounds':bb,'circles':circ});i+=1;e.Next()
(P/'inputs/cs30_customer_measurements.json').write_text(json.dumps(solids,indent=2),encoding='utf8')
print('SOLIDS',len(solids))
for s in solids:
 bb=s['bounds'];ds=[bb[j+3]-bb[j] for j in range(3)]
 if max(ds)>7 and s['circles']:print(s['index'],[round(v,3) for v in bb],s['circles'][:16])


