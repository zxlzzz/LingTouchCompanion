from pathlib import Path
import json,math
import numpy as np
from OCP.STEPControl import STEPControl_Reader
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_EDGE,TopAbs_FACE,TopAbs_REVERSED
from OCP.TopoDS import TopoDS
from OCP.BRepAdaptor import BRepAdaptor_Curve
from OCP.GeomAbs import GeomAbs_Circle
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRep import BRep_Tool
from OCP.TopLoc import TopLoc_Location
P=Path(__file__).resolve().parent
r=STEPControl_Reader();r.ReadFile(str(P/'inputs/CS30_customer.stp'));r.TransferRoots();shape=r.OneShape()
circles=[];e=TopExp_Explorer(shape,TopAbs_EDGE)
while e.More():
 c=BRepAdaptor_Curve(TopoDS.Edge(e.Current()))
 if c.GetType()==GeomAbs_Circle:
  a=c.Circle();q=a.Location();n=a.Axis().Direction()
  circles.append(tuple(round(z,7) for z in [q.X(),q.Y(),q.Z(),a.Radius(),n.X(),n.Y(),n.Z()]))
 e.Next()
circles=sorted(set(circles));(P/'inputs/customer_all_circles.json').write_text(json.dumps(circles,indent=2),encoding='utf8')
print('Optical front circles:')
for c in circles:
 if c[2]>-1.001 and abs(c[1])<.1 and abs(abs(c[-1])-1)<1e-5:print(c)
BRepMesh_IncrementalMesh(shape,.04,False,.15,True).Perform()
vs=[];fs=[];e=TopExp_Explorer(shape,TopAbs_FACE)
while e.More():
 face=TopoDS.Face(e.Current());loc=TopLoc_Location();mesh=BRep_Tool.Triangulation_s(face,loc)
 if mesh is not None:
  off=len(vs);tr=loc.Transformation()
  for i in range(1,mesh.NbNodes()+1):
   p=mesh.Node(i).Transformed(tr);vs.append([p.X(),p.Y(),p.Z()])
  for i in range(1,mesh.NbTriangles()+1):
   a,b,c=mesh.Triangle(i).Get();t=[off+a-1,off+b-1,off+c-1];fs.append(t[::-1] if face.Orientation()==TopAbs_REVERSED else t)
 e.Next()
v=np.array(vs);f=np.array(fs);np.savez_compressed(P/'inputs/camera_official_source.npz',v=v,f=f)
print('Triangulated face bounds:',v.min(0),v.max(0),'dims',v.max(0)-v.min(0),'faces',len(f))
