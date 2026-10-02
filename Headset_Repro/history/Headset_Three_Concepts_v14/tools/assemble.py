"""Add editable routed cables, structural cable keepers, strain relief, then export evaluation meshes."""
import bpy,sys,json,math,numpy as np,trimesh
from pathlib import Path
from mathutils import Matrix,Vector
from mathutils.bvhtree import BVHTree
from cad_kernel import *
from scipy.spatial import cKDTree
P=Path(__file__).parent;D=P.parent/sys.argv[1];K=sys.argv[1]
bpy.ops.wm.open_mainfile(filepath=str(D/'working.blend'),load_ui=False,use_scripts=False)
bpy.context.preferences.filepaths.save_version=0
design=json.loads((D/'design_data.json').read_text(encoding='utf-8'));routes=json.loads((D/'routes.json').read_text());cam=bpy.data.objects['MOVE__CS30'];cc=np.array(cam.location);scene=bpy.context.scene
SC=bpy.data.collections['09_Printable_Structure'];WC=bpy.data.collections['10_Wiring'];HC=bpy.data.collections['11_Hardware_and_Soft_Parts']
for n,c in {'Cable_black':(.01,.012,.014,1),'Cable_signal':(.49,.19,.07,1),'Cable_speaker':(.10,.32,.48,1),'Fastener':(.28,.31,.34,1)}.items():
 if n not in bpy.data.materials:
  ma=bpy.data.materials.new(n);ma.diffuse_color=c
def update():scene.frame_set(1);bpy.context.view_layer.update()
def meshdata(o):
 eo=o.evaluated_get(bpy.context.evaluated_depsgraph_get());me=eo.to_mesh();me.calc_loop_triangles();v=np.array([eo.matrix_world@p.co for p in me.vertices]);f=np.array([t.vertices[:] for t in me.loop_triangles]);eo.to_mesh_clear();return v,f
def solidof(o):
 v,f=meshdata(o);tm=trimesh.Trimesh(v,f,process=True);tm.merge_vertices(digits_vertex=5);mm=md.Mesh(np.ascontiguousarray(tm.vertices,np.float32),np.ascontiguousarray(tm.faces,np.uint32));so=M(mm)
 if str(so.status())!='Error.NoError':raise RuntimeError(o.name+' '+str(so.status()))
 return so
def putmesh(o,solid):
 solid=union([q for q in solid.decompose() if q.volume()>1e-6]);m=solid.to_mesh();me=bpy.data.meshes.new(o.name);me.from_pydata(np.asarray(m.vert_properties)[:,:3].tolist(),[],np.asarray(m.tri_verts).tolist());me.update();mats=list(o.data.materials);o.data=me
 for mat in mats:me.materials.append(mat)
 o['volume_mm3']=solid.volume();return o
def obsolid(n,solid,mat='Inner_carrier',kind='structure',coll=SC):
 o=bpy.data.objects.new(n,bpy.data.meshes.new(n));coll.objects.link(o);putmesh(o,solid);o.data.materials.append(bpy.data.materials[mat]);o['export_physical']=True;o['part_category']=kind;return o
def makecurve(n,segs,r,mat,weights=None,alternate=None):
 cu=bpy.data.curves.new(n,'CURVE');cu.dimensions='3D';cu.resolution_u=20;cu.bevel_depth=r;cu.bevel_resolution=3;cu.use_fill_caps=True
 sp=cu.splines.new('BEZIER');sp.bezier_points.add(len(segs));o=bpy.data.objects.new(n,cu);WC.objects.link(o);cu.materials.append(bpy.data.materials[mat]);o['export_physical']=True;o['part_category']='wire'
 for i,p in enumerate(sp.bezier_points):
  p.handle_left_type='FREE';p.handle_right_type='FREE';p.co=segs[min(i,len(segs)-1)][0] if i<len(segs) else segs[-1][-1]
  p.handle_left=segs[i-1][2] if i else segs[0][0]-(segs[0][1]-segs[0][0]);p.handle_right=segs[i][1] if i<len(segs) else segs[-1][-1]+(segs[-1][-1]-segs[-1][-2])
  if (weights is not None and weights[i]>1e-9) or alternate is not None:
   w=weights[i] if weights is not None else 0
   for attr in ['co','handle_left','handle_right']:
    xyz=np.array(getattr(p,attr));yy=xyz[1]-cc[1];zz=xyz[2]-cc[2]
    exprs=[(1,f'{xyz[1]}+{w}*({yy}*cos((p+20)*pi/180)-{zz}*sin((p+20)*pi/180)-{yy})'),(2,f'{xyz[2]}+{w}*({yy}*sin((p+20)*pi/180)+{zz}*cos((p+20)*pi/180)-{zz})')]
    if alternate is not None:
     if attr=='co':alt=alternate[i][0] if i<len(alternate) else alternate[-1][-1]
     elif attr=='handle_left':alt=alternate[i-1][2] if i else alternate[0][0]-(alternate[0][1]-alternate[0][0])
     else:alt=alternate[i][1] if i<len(alternate) else alternate[-1][-1]+(alternate[-1][-1]-alternate[-1][-2])
     d20=math.radians(20);delta=[0,yy*math.cos(d20)-zz*math.sin(d20)-yy,yy*math.sin(d20)+zz*math.cos(d20)-zz]
     exprs=[(ax,f'{xyz[ax]}+(p+20)/20*{alt[ax]-xyz[ax]}'+(f'+{w}*('+ex.split(f'{xyz[ax]}+{w}*(')[1][:-1]+f'-(p+20)/20*{delta[ax]})' if ax>0 else '')) for ax,ex in [(0,''),*exprs]]
    for axis,expr in exprs:
     fc=p.driver_add(attr,axis);dv=fc.driver.variables.new();dv.name='p';dv.type='SINGLE_PROP';dv.targets[0].id=cam;dv.targets[0].data_path='["pitch_deg"]';fc.driver.expression=expr
 return o
def sample(segs,n=12):
 t=np.linspace(0,1,n)[:,None];return np.vstack([(1-t)**3*c[0]+3*(1-t)**2*t*c[1]+3*(1-t)*t*t*c[2]+t**3*c[3] for c in segs])
def nearest(tree,p):return np.array(tree.find_nearest(Vector(p))[0])
wireobjects=[];route_samples={};weightslog={}
for name,row in routes.items():
 segs=np.array(row['segments']);knots=np.vstack([segs[:,0],segs[-1][-1]]);lens=np.r_[0,np.cumsum([np.linalg.norm(sample([s],30)[1:]-sample([s],30)[:-1],axis=1).sum() for s in segs])]
 wa=design['leads'][row['a']]['owner'] in ['MOVE__CS30','MOVE__ICM42688P_LogicalEdges'];wb=design['leads'][row['b']]['owner'] in ['MOVE__CS30','MOVE__ICM42688P_LogicalEdges'];weights=None
 if wa or wb:
  dd=lens if wa else lens[-1]-lens;u=np.clip((dd-10)/85,0,1);weights=1-3*u*u+2*u*u*u
  weightslog[name]=weights.tolist()
 mat='Cable_speaker' if 'SPEAKER' in name else 'Cable_black' if row['radius_mm']>1 else 'Cable_signal'
 alt=np.array(json.loads((D/'camera_zero.json').read_text())['segments']) if name=='USB_Camera' else None
 o=makecurve('WIRE__'+name,segs,row['radius_mm'],mat,weights,alt);o['from']=row['a'];o['to']=row['b'];o['minimum_design_radius_mm']=row['criterion_radius_mm'];wireobjects.append(o);route_samples[name]=sample(segs,18)
update()
(D/'wire_motion_weights.json').write_text(json.dumps(weightslog,indent=2))
if '--preview' in sys.argv:
 bpy.ops.wm.save_as_mainfile(filepath=str(D/'routed.blend'));sys.exit()

# Carved passage slots prevent the routed insulation from occupying an outer lid or rail.
# Tube thickness is retained in independent wire objects; these cuts are only structural clearance.
cutsolids=[]
for ob in wireobjects:
 old=ob.data.bevel_depth;ob.data.bevel_depth=old+.45;update();cutsolids.append(solidof(ob));ob.data.bevel_depth=old
update();wirecuts=union(cutsolids)
for ob in list(SC.objects):
 if ob.type=='MESH' and ob.name.startswith(('OUTER__','INNER__Main')):
  so=solidof(ob);putmesh(ob,so-wirecuts)

carrier=bpy.data.objects['INNER__Main_load_carrier'];base=solidof(carrier);cv,cf=meshdata(carrier);tree=BVHTree.FromPolygons([Vector(q) for q in cv],cf.tolist(),all_triangles=True)
battery=bpy.data.objects['BATTERY__Independent_cradle'];bsolid=solidof(battery);bv,bf=meshdata(battery);btree=BVHTree.FromPolygons([Vector(q) for q in bv],bf.tolist(),all_triangles=True)
occupied=[]
for ob in bpy.data.objects:
 if ob.type!='MESH' or not ob.get('export_physical') or ob.get('part_category','component') not in ['component','component_case'] or ob.name.startswith('CS30__OFFICIAL'):continue
 owner=ob
 while owner.parent and not owner.name.startswith('MOVE__'):owner=owner.parent
 R=np.array(owner.matrix_world);iv=np.linalg.inv(R);v,f=meshdata(ob);lv=v@iv[:3,:3].T+iv[:3,3];lo=lv.min(0);hi=lv.max(0);occupied.append(tf(box(hi-lo+.6,(lo+hi)/2),R))
occupied=union(occupied)
guides=[];guide_notes=[]
# Short, detachable C-keepers retain the routed runs against the inner assembly. Moving leads are free near the hinge.
selected=['MIC_VDD','MIC_SCK','AMP_DIN','IMU_1','USB_Data','USB_Camera','SPEAKER_LINK_PLUS','SPEAKER_FACTORY_PLUS','POWER_1','POWER_2']
for name in selected:
 row=routes[name];pts=route_samples[name];dist=np.r_[0,np.cumsum(np.linalg.norm(np.diff(pts,axis=0),axis=1))];wanted=np.arange(25,dist[-1]-18,38 if row['radius_mm']>1 else 55)
 if 'POWER' in name:
  last=row['service_segment_range'][1];pts=sample(np.array(row['segments'])[last:],18);dist=np.r_[0,np.cumsum(np.linalg.norm(np.diff(pts,axis=0),axis=1))];wanted=np.arange(25,dist[-1]-15,38)
 for j,l in enumerate(wanted):
  idx=int(np.argmin(abs(dist-l)));p=pts[idx];t=pts[min(idx+1,len(pts)-1)]-pts[max(0,idx-1)];t/=np.linalg.norm(t);q=nearest(tree,p);inward=q-p;span=np.linalg.norm(inward)
  if span<2 or span>36:continue
  if name in ['USB_Camera','IMU_1'] and (np.linalg.norm(p-pts[0 if name=='USB_Camera' else -1])<50):continue
  inward/=span;rr=row['radius_mm']+.35;ring=cyl(rr+1.6,4,p-t*2,t)-cyl(rr,6,p-t*3,t)
  # The slot faces away from the load carrier, permitting lateral insertion of a terminated cable.
  F=axis_frame(p,-inward);ring-=tf(box((rr*1.4,7,rr+4),(0,0,(rr+4)/2)),F)
  support=capsule(p+inward*(rr+1.1),q,1.6);guides.append(ring+support);guide_notes.append(dict(route=name,station_mm=float(l),support_span_mm=float(span)))
if guides:base+=(union(guides)-wirecuts)-occupied

# Two rigid relief locations on each supply cable, fixed independently to battery tray and mirror carrier.
clamp_notes=[]
for name in ['POWER_1','POWER_2']:
 row=routes[name]
 for j,p in enumerate(row['clamps']):
  p=np.array(p);F=axis_frame(p,[0,0,1]);block=box((13,10,8))-cyl(1.6,10,(0,0,-5));bolts=union([cyl(1.1,16,(-8,y,0),(1,0,0)) for y in [-3.8,3.8]]);block-=bolts
  basehalf=tf(block-box((15,20,20),(7.5,0,0)),F);cap=tf(block-box((15,20,20),(-7.5-.2,0,0)),F)
  target=btree if j==0 else tree;q=nearest(target,p);u=(q-p);u/=np.linalg.norm(u);bracket=capsule(p+u*5,q,2.1)
  if j==0:bsolid+=(basehalf+bracket)-occupied
  else:base+=(basehalf+bracket)-occupied
  obsolid('RELIEF__'+name+('_battery_cap' if j==0 else '_mirror_cap'),cap,'Inner_carrier');clamp_notes.append(dict(cable=name,end='battery' if j==0 else 'mirror',position=p.tolist()))
 # Fabric keeper sleeve lies behind the extensible S; it stretches with the elastic, rather than linking the two clamps rigidly.
 a,b=np.array(row['clamps']);u=(b-a)/np.linalg.norm(b-a);v=np.array([0.,0.,1.]);normal=np.cross(u,v);T=np.eye(4);T[:3,:3]=np.column_stack([u,normal,v]);T[:3,3]=(a+b)/2-normal*2.3
 sleeve=tf(box((88,.6,48)),T)
 obsolid('SOFT__'+name+'_stretch_sleeve',sleeve,'Soft_band','soft',HC)

# Clearance is cut in guide brackets, while cable clamp bores retain their explicit sizes.
base-=wirecuts;bsolid=bsolid-wirecuts-occupied

# Captive M2 fasteners are reached from the inner side; every outer boss has a blind insert bore.
fastening=[]
def fasten(lid,p,n,label):
 global base
 p=np.array(p);n=np.array(n);F=axis_frame(p,n);boss=cyl(3.6,8.3,(0,0,-8))-cyl(1.6,4.5,(0,0,-8.05));flange=cyl(4.1,2,(0,0,-10.2))-cyl(1.15,3,(0,0,-10.5))
 wboss=tf(boss,F);wflange=tf(flange,F);attach=p-n*9.2;q=nearest(tree,attach);arm=capsule(attach,q,2.3)
 if (wboss^occupied).volume()>.02:return False
 putmesh(lid,solidof(lid)+wboss)
 base+=(wflange+arm)-occupied-wirecuts
 insert=cyl(1.57,4,(0,0,-7.95))-cyl(1.0,4.2,(0,0,-8.05));screw=cyl(.96,6,(0,0,-10.2))+cyl(1.85,1.6,(0,0,-11.8))
 obsolid('M2__'+label+'_insert',tf(insert,F),'Fastener','hardware',HC);obsolid('M2__'+label+'_screw',tf(screw,F),'Fastener','hardware',HC)
 fastening.append(dict(lid=lid.name,axis=n.tolist(),position=p.tolist(),screw='M2x6',insert='M2 OD3.2 x 4mm, blind'))
 return True
for lid in [o for o in SC.objects if o.type=='MESH' and o.name.startswith('OUTER__')]:
 if K=='A':
  vv,ff=meshdata(lid);lt=BVHTree.FromPolygons([Vector(p) for p in vv],ff.tolist(),all_triangles=True)
  for i,(start,n) in enumerate([([66,0,10],[0,1,0]),([-66,0,10],[0,1,0]),([0,-45,48],[1,0,0]),([0,-45,48],[-1,0,0])]):
   h=lt.ray_cast(Vector(start),Vector(n))
   if h[0]:fasten(lid,np.array(h[0]),n,'A_'+str(i))
 else:
  owner='MOVE__'+lid.name[len('OUTER__'):-len('_cover')];R=np.array(bpy.data.objects[owner].matrix_world);iv=np.linalg.inv(R);vv,ff=meshdata(lid);loc=vv@iv[:3,:3].T+iv[:3,3];lo=loc.min(0);hi=loc.max(0)
  for j,edge in enumerate([lo[0],hi[0]]):
   x=edge+(-2.8 if j==0 else 2.8);z=hi[2]-2
   bridge=tf(box((10,8,2),(edge,0,hi[2]-1)),R);putmesh(lid,solidof(lid)+bridge)
   fasten(lid,R[:3,:3]@np.array([x,0,z])+R[:3,3],R[:3,2],K+'_'+owner+'_'+str(j))
headavoid=union([ellipsoid(np.array(r)+.3,c,64) for c,r in [((0,0,0),(78,96,116)),((77,-15,-15),(8,17,27)),((-77,-15,-15),(8,17,27)),((0,92,-18),(12,20,23))]])
if K=='A':
 # A short sealed pickup duct exits through the face-side wall; the microphone remains flat and downward facing.
 Rmic=np.array(bpy.data.objects['MOVE__INMP441'].matrix_world);src=(Rmic@np.array([0,0,-4.4,1]))[:3];rho=np.linalg.norm(src/np.array([81.,99.,119.]));tip=src/rho;direction=(tip-src)/np.linalg.norm(tip-src);end=tip+direction*.7
 tube=cyl(3.2,np.linalg.norm(end-src),src,direction);bore=cyl(1.5,np.linalg.norm(end-src)+4,src-direction*2,direction);base=(base+(tube-occupied-headavoid))-bore
 Rs=np.array(bpy.data.objects['MOVE__Speaker_27859'].matrix_world);base-=tf(box((19,10,60),(0,0,31)),Rs)
def connect_parts(solid,label):
 parts=sorted([s for s in solid.decompose() if s.volume()>1],key=lambda p:p.volume(),reverse=True);main=parts.pop(0);fail=[]
 for piece in parts:
  bv=np.asarray(main.to_mesh().vert_properties)[:,:3];pv=np.asarray(piece.to_mesh().vert_properties)[:,:3];pv=pv[::max(1,len(pv)//160)];bv=bv[::max(1,len(bv)//12000)];kd=cKDTree(bv);ds,ix=kd.query(pv,k=5);pairs=sorted([(ds[i,j],pv[i],bv[ix[i,j]]) for i in range(len(pv)) for j in range(5)],key=lambda z:z[0]);joined=False
  for distance,p,q in pairs[:70]:
   if distance>65:continue
   bridge=capsule(p,q,1.8)-occupied-wirecuts-headavoid;candidate=main+piece+bridge;ps=[x for x in candidate.decompose() if x.volume()>1]
   if len(ps)==1:main=ps[0];joined=True;break
  if not joined:
   # Reach the inner rail around the end of the main board, preserving its entire cooling face.
   candidates=pv[np.argsort(pv[:,0])[-8:]]
   for yy in [-42.,-47.,42.,49.]:
    dest=bv[(abs(bv[:,1]-yy)<12)&(bv[:,0]>45)]
    if not len(dest):continue
    for p in candidates:
     ds=np.linalg.norm(dest-p,axis=1);choices=dest[np.argsort(ds)[:5]]
     for q in choices:
      points=[p,np.array([p[0],yy,p[2]]),np.array([q[0],yy,q[2]]),q]
      bridge=union([capsule(a,b,1.8) for a,b in zip(points[:-1],points[1:]) if np.linalg.norm(b-a)>.01])-occupied-wirecuts-headavoid
      candidate=main+piece+bridge;ps=[x for x in candidate.decompose() if x.volume()>1]
      if len(ps)==1:main=ps[0];joined=True;break
     if joined:break
    if joined:break
  if not joined:fail.append(piece);print('UNJOINED',label,piece.volume(),piece.bounding_box(),flush=True)
 print('CONNECTIVITY',label,len(fail)+1,flush=True)
 return union([main]+fail)
base=connect_parts(base,'inner');bsolid=connect_parts(bsolid,'battery')
for ob in [o for o in SC.objects if o.type=='MESH' and o.name.startswith('OUTER__')]:
 so=solidof(ob);parts=sorted(so.decompose(),key=lambda q:q.volume(),reverse=True)
 if len(parts)>1:putmesh(ob,union([p for i,p in enumerate(parts) if i==0 or p.volume()>100]))
putmesh(carrier,base);putmesh(battery,bsolid)
(D/'fasteners.json').write_text(json.dumps(fastening,indent=2))
(D/'retention_details.json').write_text(json.dumps(dict(guides=guide_notes,power_clamps=clamp_notes),indent=2))

def snapshot(tag):
 update();obdata={};arrays={}
 for ob in bpy.data.objects:
  if ob.type not in ['MESH','CURVE'] or not(ob.get('export_physical') or ob.name in ['REF_head','REF_ear_L','REF_ear_R','REF_nose']):continue
  v,f=meshdata(ob)
  if len(v)==0:continue
  own=ob
  while own.parent and not own.name.startswith('MOVE__'):own=own.parent
  obdata[ob.name]=dict(owner=own.name,category=ob.get('part_category','component'),bounds=[v.min(0).tolist(),v.max(0).tolist()]);arrays[ob.name+'__v']=v;arrays[ob.name+'__f']=f
 np.savez_compressed(D/(tag+'_meshes.npz'),**arrays);(D/(tag+'_objects.json')).write_text(json.dumps(obdata,indent=2))
snapshot('final');bpy.ops.wm.save_as_mainfile(filepath=str(D/('Concept_'+K+'.blend')))
print('ASSEMBLED',K,flush=True)
