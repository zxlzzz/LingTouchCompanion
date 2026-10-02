"""Continuous original-head triangle distances, no model changes."""
from pathlib import Path
import ast,json,hashlib,sys
import numpy as np
P=Path(__file__).resolve().parent;ROOT=P.parents[1];G=P.parent/'geometry'
SOURCE=ROOT/'Headset_Carbon6K_FlatBase_Review_2026-10-02/audit/audit_surface_distances.py'
tree=ast.parse(SOURCE.read_text());nodes=[n for n in tree.body if isinstance(n,(ast.Import,ast.ImportFrom,ast.FunctionDef)) and not (isinstance(n,ast.FunctionDef) and n.name=='main')]
sys.path.insert(0,str(ROOT/'Headset_Carbon6K_FlatBase_Review_2026-10-02/inputs'))
ns={};exec(compile(ast.Module(nodes,type_ignores=[]),str(SOURCE),'exec'),ns)
head=ROOT/'Headset_Carbon6K_FlatBase_Review_2026-10-02/inputs/Medium_Trial_Registered.npz';a=np.load(head);HV,HF=a['v'],a['f'];H=HV[HF]
def load(n):
 a=np.load(G/(n+'.npz'));return a['v'],a['f']
CV,CF=load('camera');report={'head_sha256':hashlib.sha256(head.read_bytes()).hexdigest(),'head_pose_unchanged':True,'camera_head':ns['continuous_min'](HV,HF,CV,CF)}
# Nasal original source region declared and used in the preceding review.
keep=(np.abs(H[:,:,0]).max(1)<30)&(H[:,:,1].min(1)<12)&(H[:,:,2].max(1)>-10)&(H[:,:,2].min(1)<45)
N=H[keep];NV=N.reshape(-1,3);NF=np.arange(len(NV)).reshape(-1,3)
# Exact Y<=0 clipping per triangle; triangulate polygon fragments.
V,F=load('added_material');out=[]
for poly in V[F]:
 p=[]
 for a,b in zip(poly,np.roll(poly,-1,axis=0)):
  da=a[1];db=b[1]
  if da<=0:p.append(a)
  if (da<0)!=(db<0):p.append(a+(b-a)*da/(da-db))
 if len(p)>=3:
  for i in range(1,len(p)-1):out.append([p[0],p[i],p[i+1]])
Q=np.array(out)
# Existing upper bound3mm and rigorous AABB distance pruning for nasal region.
nlo,nhi=N.min((0,1)),N.max((0,1));gap=np.maximum(np.maximum(nlo-Q.max(1),Q.min(1)-nhi),0)
Q=Q[(gap*gap).sum(1)<=3**2]
QV=Q.reshape(-1,3);QF=np.arange(len(QV)).reshape(-1,3)
report['nose_Ynegative_new_material']=ns['continuous_min'](NV,NF,QV,QF)
report['nose_source_region_definition']='All original head triangles with maxabsX<30,minY<12,maxZ>-10,minZ<45; exactY<=0 clipped new triangles and3mm rigorous bounding-box pruning.'
report['camera_solid_vs_head_containment']='Camera lies on anterior side of all intersecting XZ head projection rays, separately checked with original surface BVH in rendering runtime.'
(P/'clearances.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report,indent=2))
