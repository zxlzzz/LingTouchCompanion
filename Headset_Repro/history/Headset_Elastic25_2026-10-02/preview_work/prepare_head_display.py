from pathlib import Path
import numpy as np
import trimesh
ROOT=Path(__file__).resolve().parents[1]
a=np.load(ROOT.parent/'Headset_FullCase_30mm_Preview_2026-10-02/headform/Medium_Trial_Registered.npz')
head=trimesh.Trimesh(a['v'],a['f'],process=False)
v=head.vertices;f=head.faces;tz=v[f,2]
faces=f[(tz>=-20).all(axis=1)].tolist();vertices=v.tolist()
for face in f[(tz.max(axis=1)>=-20)&(tz.min(axis=1)<-20)]:
 poly=[(int(k),v[k]) for k in face];result=[]
 for a,b in zip(poly,poly[1:]+poly[:1]):
  ai=a[1][2]>=-20;bi=b[1][2]>=-20
  if ai:result.append(a[0])
  if ai!=bi:
   p=a[1]+(b[1]-a[1])*((-20-a[1][2])/(b[1][2]-a[1][2]))
   result.append(len(vertices));vertices.append(p.tolist())
 for i in range(1,len(result)-1):faces.append([result[0],result[i],result[i+1]])
head=trimesh.Trimesh(vertices,faces,process=False);head.remove_unreferenced_vertices()
np.savez_compressed(ROOT/'preview_work/head_display.npz',v=head.vertices,f=head.faces)
print('Anatomical head display only: clipped neck below Z=-20; original registration unchanged.')
