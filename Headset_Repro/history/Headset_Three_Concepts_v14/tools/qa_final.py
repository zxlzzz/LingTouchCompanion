import bpy,sys,json,numpy as np,math,itertools,ast
from pathlib import Path
from mathutils import Vector,Matrix
from mathutils.bvhtree import BVHTree
P=Path(__file__).parent;D=P.parent/sys.argv[1];K=sys.argv[1]
from scipy.integrate import quad
src=ast.parse((P/'routes.py').read_text(encoding='utf-8'));sel=ast.Module(body=[n for n in src.body if isinstance(n,ast.FunctionDef) and n.name in ['exact_radius','metrics','sample']],type_ignores=[]);exec(compile(sel,'curvature','exec'))
bpy.ops.wm.open_mainfile(filepath=str(D/('Concept_'+K+'.blend')),load_ui=False,use_scripts=False);cam=bpy.data.objects['MOVE__CS30'];scene=bpy.context.scene
design=json.loads((D/'design_data.json').read_text(encoding='utf-8'));routes=json.loads((D/'routes.json').read_text())
def meshes():
 scene.frame_set(1);bpy.context.view_layer.update();dg=bpy.context.evaluated_depsgraph_get();out={}
 for ob in bpy.data.objects:
  if ob.type not in ['MESH','CURVE'] or not (ob.get('export_physical') or ob.name in ['REF_head','REF_ear_L','REF_ear_R','REF_nose']):continue
  eo=ob.evaluated_get(dg);me=eo.to_mesh();me.calc_loop_triangles();v=np.array([eo.matrix_world@q.co for q in me.vertices]);f=np.array([t.vertices[:] for t in me.loop_triangles]);eo.to_mesh_clear()
  if not len(v):continue
  owner=ob
  while owner.parent and not owner.name.startswith('MOVE__'):owner=owner.parent
  out[ob.name]=dict(owner=owner.name,category=ob.get('part_category','component'),v=v,f=f,lo=v.min(0),hi=v.max(0),tree=BVHTree.FromPolygons([Vector(q) for q in v],f.tolist(),all_triangles=True,epsilon=1e-6))
 return out
def inside(p,d):
 if np.any(p<=d['lo']+1e-3) or np.any(p>=d['hi']-1e-3):return False
 near=d['tree'].find_nearest(Vector(p))
 if near[0] is None or near[3]<.025:return False
 votes=[]
 for dd in [(1,.123,.345),(.23,1,.532),(.17,.432,1)]:
  pos=Vector(p);direction=Vector(dd).normalized();count=0
  for i in range(1000):
   hit=d['tree'].ray_cast(pos,direction)
   if hit[0] is None:break
   count+=1;pos=hit[0]+direction*.001
  votes.append(count%2==1)
 return sum(votes)>=2
def overlap(a,b):
 if np.any(a['hi']<=b['lo']+1e-4) or np.any(b['hi']<=a['lo']+1e-4):return False
 if a['tree'].overlap(b['tree']):return True
 return any(inside(p,b) for p in a['v'][[0,len(a['v'])//2,-1]]) or any(inside(p,a) for p in b['v'][[0,len(b['v'])//2,-1]])
def collisions(objs):
 result=dict(devices=[],device_shell=[],head=[],wire_devices=[],wire_head=[])
 for (na,a),(nb,b) in itertools.combinations(objs.items(),2):
  ca=a['category'];cb=b['category']
  if ca=='hardware' or cb=='hardware':continue
  if na.startswith('REF_') or nb.startswith('REF_'):
   if na.startswith('REF_') and nb.startswith('REF_'):continue
   nn,non=(nb,b) if na.startswith('REF_') else (na,a)
   if non['category']=='soft':continue
   if overlap(a,b):result['wire_head' if non['category']=='wire' else 'head'].append([na,nb])
   continue
  if a['owner']==b['owner']:continue
  if set([a['owner'],b['owner']])==set(['MOVE__Radxa_ZERO_3W','MOVE__Heatsink_5519A']):continue
  if ca.startswith('component') and cb.startswith('component'):
   if overlap(a,b):result['devices'].append([na,nb])
  elif (ca.startswith('component') and cb=='structure') or (cb.startswith('component') and ca=='structure'):
   if overlap(a,b):result['device_shell'].append([na,nb])
  elif (ca.startswith('component') and cb=='wire') or (cb.startswith('component') and ca=='wire'):
   wn,w=(na,a) if ca=='wire' else (nb,b);pn,part=(nb,b) if ca=='wire' else (na,a);r=routes[wn[6:]];ends=[design['leads'][r[k]]['owner'] for k in ['a','b']]
   if part['owner'] in ends:continue # intentional endpoint insertion checked separately by route clearance
   if overlap(a,b):result['wire_devices'].append([na,nb])
 return result
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
exclude={'CS30__OFFICIAL_STEP_MESH','CS30_FINISHED_CASE__89p94x30x25','CS30_optical_face_-22','CS30_optical_face_22','CS30_IR_emitter_face'}
allf=[];allbend=[];col={};bounds={}
for tilt in range(21):
 cam['pitch_deg']=-float(tilt);cam.update_tag();objs=meshes();R=np.array(cam.matrix_world.to_3x3());center=np.array(cam.matrix_world.translation)
 if tilt in [0,20]:
  col[str(tilt)]=collisions(objs);print('COLLISIONS',tilt,col[str(tilt)],flush=True)
 for label,h,v,x in [('depth',100,75,22),('color',97,95.5,-22)]:
  origin=np.array([x,2.5,12.5]);worldorigin=origin@R.T+center;th=math.tan(math.radians(h/2));tv=math.tan(math.radians(v/2));planes=[np.array(q) for q in [(0,0,1),(1,0,th),(-1,0,th),(0,1,tv),(0,-1,tv)]];hits=[]
  for n,d in objs.items():
   if n in exclude or d['v'][:,1].max()<worldorigin[1]-1e-6:continue
   p=(d['v']-center)@R-origin;tris=p[d['f']];mask=np.ones(len(tris),bool)
   for normal in planes:mask &= np.max(tris@normal,axis=1)>=-1e-7
   if any(clip(list(tris[i]),planes) for i in np.where(mask)[0]):hits.append(n)
  allf.append(dict(downward_pitch_deg=tilt,view=label,H=h,V=v,hits=hits,passed=not hits))
 dg=bpy.context.evaluated_depsgraph_get()
 for name,row in routes.items():
  ob=bpy.data.objects['WIRE__'+name].evaluated_get(dg);bp=ob.data.splines[0].bezier_points;segs=np.array([[bp[i].co,bp[i].handle_right,bp[i+1].handle_left,bp[i+1].co] for i in range(len(bp)-1)]);mt=metrics(segs);allbend.append(dict(name=name,pitch=tilt,**mt,criterion_mm=row['criterion_radius_mm'],passed=mt['min_radius_mm']>=row['criterion_radius_mm']-.01))
 if tilt==20:
  vv=np.vstack([o['v'] for n,o in objs.items() if not n.startswith('REF_')]);bounds=dict(min=vv.min(0).tolist(),max=vv.max(0).tolist(),size_mm=np.ptp(vv,axis=0).tolist())
 print('CHECKED ANGLE',tilt,flush=True)
# Continuous-angle visibility witness. Every stated FOV ray has positive world Y at 0..20 deg.
# Rigid camera children stay behind their optical plane. For all other geometry, bound maximum Y.
optic_y_min=float(center[1]+12.5*math.cos(math.radians(20))-2.5*math.sin(math.radians(20)))
continuum=[]
for n,o in objs.items():
 if n in exclude or o['category']=='wire':continue
 if o['owner'] in ['MOVE__CS30','MOVE__ICM42688P_LogicalEdges']:
  zmax=float(((o['v']-center)@R)[:,2].max());continuum.append(dict(object=n,method='Rigid child behind optical plane',margin_mm=12.5-zmax,passed=zmax<=12.5+1e-5))
 else:continuum.append(dict(object=n,method='Static geometry behind minimum optical world Y',margin_mm=optic_y_min-float(o['hi'][1]),passed=o['hi'][1]<optic_y_min))
angles=np.linspace(0,math.radians(20),4);Cmat=np.array([[1,x,math.cos(x),math.sin(x)] for x in angles]);wire_y={n:[] for n in routes}
for d in angles:
 cam['pitch_deg']=math.degrees(d)-20;cam.update_tag();scene.frame_set(1);bpy.context.view_layer.update();dg=bpy.context.evaluated_depsgraph_get()
 for n in routes:
  bp=bpy.data.objects['WIRE__'+n].evaluated_get(dg).data.splines[0].bezier_points
  wire_y[n].append(np.array([getattr(p,a)[1] for p in bp for a in ['co','handle_left','handle_right']]))
for n,vals in wire_y.items():
 co=np.linalg.solve(Cmat,np.array(vals));maximum=-1e9
 for D0,L,A,B in co.T:
  ts=[0.,angles[-1]];rr=math.hypot(A,B)
  if rr>1e-9 and abs(L/rr)<=1:
   phase=math.atan2(A,B);root=math.acos(-L/rr)
   for sign in [-1,1]:
    for turn in [-1,0,1]:
     x=sign*root-phase+2*math.pi*turn
     if 0<x<angles[-1]:ts.append(x)
  maximum=max(maximum,max(D0+L*x+A*math.cos(x)+B*math.sin(x) for x in ts))
 maximum+=routes[n]['radius_mm']+.02
 continuum.append(dict(object='WIRE__'+n,method='Analytic extrema of driven cubic control hull, plus cable radius and 0.02 mm numerical allowance',margin_mm=optic_y_min-maximum,passed=maximum<optic_y_min))
res=dict(collisions_at_pitch=col,fov_checks=allf,continuous_fov_bound=dict(passed=all(x['passed'] for x in continuum),minimum_optical_world_Y=optic_y_min,checks=continuum),bend_checks=allbend,assembly_bounds=bounds,methods='Device collisions: triangle BVH plus three-ray majority containment at 0 and 20 deg, excluding same-device assembly contacts and fasteners. FOV: exact triangle clipping at each integer degree, plus analytic rear-plane bounds over the continuous 0..20 interval. Cable radius: extrema of each cubic Bezier span at the 21 evaluated angles. Physical cable specification, wire-wire contact, thermal performance, and printed fit are not checked.')
(D/'checks.json').write_text(json.dumps(res,indent=2,default=lambda x:x.item() if isinstance(x,np.generic) else str(x)));print('FOV FAILURES',[x for x in allf if not x['passed']],flush=True);print('CONTINUOUS BOUND FAILURES',[x for x in continuum if not x['passed']],flush=True);print('BEND FAILURES',[(x['name'],x['pitch'],round(x['min_radius_mm'],2)) for x in allbend if not x['passed']],flush=True)
