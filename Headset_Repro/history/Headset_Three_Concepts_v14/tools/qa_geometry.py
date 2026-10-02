import bpy,sys,json,numpy as np,math,itertools
from pathlib import Path
from mathutils import Vector,Matrix
from mathutils.bvhtree import BVHTree
P=Path(__file__).parent;D=P.parent/sys.argv[1]
meta=json.loads((D/'working_objects.json').read_text());arr=np.load(D/'working_meshes.npz');design=json.loads((D/'design_data.json').read_text(encoding='utf-8'))
objs={}
for n,m in meta.items():
 v=arr[n+'__v'];f=arr[n+'__f'];tree=BVHTree.FromPolygons([Vector(x) for x in v],f.tolist(),all_triangles=True,epsilon=1e-5);objs[n]=dict(m,v=v,f=f,tree=tree)
def overlap(a,b):
 if np.any(np.max(a['v'],axis=0)<np.min(b['v'],axis=0)+1e-4) or np.any(np.max(b['v'],axis=0)<np.min(a['v'],axis=0)+1e-4):return False
 return bool(a['tree'].overlap(b['tree']))
components=[];head=[];structure=[]
for (na,a),(nb,b) in itertools.combinations(objs.items(),2):
 ca=a['category'];cb=b['category']
 if ca=='hardware' or cb=='hardware':continue
 if na.startswith('REF_') or nb.startswith('REF_'):
  if na.startswith('REF_') and nb.startswith('REF_'):continue
  non=b if na.startswith('REF_') else a
  if non['category']=='soft':continue
  if overlap(a,b):head.append([na,nb])
  continue
 if a['owner']==b['owner']:continue
 if set([a['owner'],b['owner']])==set(['MOVE__Radxa_ZERO_3W','MOVE__Heatsink_5519A']):continue
 if ca.startswith('component') and cb.startswith('component'):
  if overlap(a,b):components.append([na,nb])
 elif (ca.startswith('component') and cb=='structure') or (cb.startswith('component') and ca=='structure'):
  if overlap(a,b):structure.append([na,nb])
print('COMPONENT',components,flush=True);print('HEAD',head,flush=True);print('STRUCTURE',structure,flush=True)
def clip(poly,planes):
 for normal in planes:
  out=[]
  for i,a in enumerate(poly):
   b=poly[(i+1)%len(poly)];da=a@normal;db=b@normal
   if da>=-1e-7:out.append(a)
   if (da>=0)!=(db>=0):out.append(a+(b-a)*da/(da-db))
  poly=out
  if not poly:return []
 return poly
camera=np.array(design['camera_center']);R0=np.array(Matrix.Rotation(math.radians(-110),3,'X'));fovs=[]
exclude={'CS30__OFFICIAL_STEP_MESH','CS30_FINISHED_CASE__89p94x30x25','CS30_optical_face_-22','CS30_optical_face_22','CS30_IR_emitter_face'}
for tilt in range(21):
 R=np.array(Matrix.Rotation(math.radians(-90-tilt),3,'X'));rot=R@R0.T
 for label,h,v,x in [('depth',100,75,22),('color',97,95.5,-22)]:
  origin=np.array([x,2.5,12.5]);worldorigin=origin@R.T+camera;th=math.tan(math.radians(h/2));tv=math.tan(math.radians(v/2));planes=[np.array(q) for q in [(0,0,1),(1,0,th),(-1,0,th),(0,1,tv),(0,-1,tv)]];hits=[]
  for n,d in objs.items():
   if n in exclude:continue
   points=d['v']
   if d['owner'] in ['MOVE__CS30','MOVE__ICM42688P_LogicalEdges']:points=(points-camera)@rot.T+camera
   # Every ray in both specified FOVs has positive world Y for 0..20 degrees.
   if points[:,1].max()<worldorigin[1]-1e-6:continue
   p=(points-camera)@R-origin;tris=p[d['f']];mask=np.ones(len(tris),bool)
   for normal in planes:mask &= np.max(tris@normal,axis=1)>=-1e-7
   for i in np.where(mask)[0]:
    if clip(list(tris[i]),planes):hits.append(n);break
  fovs.append(dict(downward_pitch_deg=tilt,view=label,H=h,V=v,hits=hits,passed=not hits))
res=dict(component_intersections=components,component_shell_intersections=structure,head_intersections=head,fov_checks=fovs,checked_pitch_degrees=list(range(21)),methods='Triangle BVH in world millimeters; exact frustum triangle clipping at 1 degree intervals. Same-device assembly contacts and fasteners excluded. No continuum proof or physical fit/thermal test.')
(D/'geometry_check.json').write_text(json.dumps(res,indent=2),encoding='utf-8')
print('FOV FAILS',[(r['downward_pitch_deg'],r['view'],r['hits']) for r in fovs if not r['passed']],flush=True)
