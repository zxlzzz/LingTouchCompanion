import bpy,sys,json,math,numpy as np
from pathlib import Path
from mathutils import Matrix,Vector
from cad_kernel import *
P=Path(__file__).parent;OUT=P.parent;ROOT=OUT.parent
BASE=ROOT/'Headset_Shell_v13/tools';meta=json.loads((BASE/'baseline_geometry.json').read_text());oldnp=np.load(BASE/'baseline_meshes.npz')
KEY=sys.argv[1] if len(sys.argv)>1 else 'A';DEST=OUT/KEY;DEST.mkdir(exist_ok=True)
styles={
 'A':dict(name='包覆面罩',camera=(0,128,43),shift=(9,0,0),belt_z=20,color=(.13,.20,.26,1),ref='Hicks et al. 2013 ski-goggle depth display',url='https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0067695'),
 'B':dict(name='开放眼镜框',camera=(0,122,67),shift=(8,0,18),belt_z=20,color=(.24,.32,.28,1),ref='Envision Glasses titanium / Smith Optics frame',url='https://support.letsenvision.com/hc/en-us/articles/7604953925777-Hardware-Form-and-Design'),
 'C':dict(name='头顶承重头箍',camera=(0,107,92),shift=(-8,0,60),belt_z=65,color=(.34,.25,.15,1),ref='RealWear Navigator 520 Overhead Band',url='https://shop.realwear.com/products/overhead-band')}
s=styles[KEY]
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'Headset_Layout_v12/Headset_Layout_v12.blend'),load_ui=False,use_scripts=False)
bpy.context.preferences.filepaths.save_version=0
for name in ['08_Sport_Glasses_Form']:
 coll=bpy.data.collections.get(name)
 if coll:
  for ob in list(coll.all_objects):bpy.data.objects.remove(ob,do_unlink=True)
  bpy.data.collections.remove(coll)
for ob in list(bpy.data.objects):
 if ob.name.startswith(('ROUTE__','FORM_','REF_Camera_finished','VIEW_')) and not ob.name.startswith('VIEW_'):bpy.data.objects.remove(ob,do_unlink=True)
env=bpy.data.objects['CS30_FINISHED_CASE_ENVELOPE'];env['export_physical']=False;env.hide_render=True;env.hide_set(True)
scene=bpy.context.scene
def update():scene.frame_set(1);bpy.context.view_layer.update()
def collection(name):
 c=bpy.data.collections.new(name);scene.collection.children.link(c);return c
SC=collection('09_Printable_Structure');WC=collection('10_Wiring');HC=collection('11_Hardware_and_Soft_Parts')
def material(name,color,rough=.45):
 m=bpy.data.materials.new(name);m.diffuse_color=color;m.use_nodes=True;bs=m.node_tree.nodes.get('Principled BSDF');bs.inputs['Base Color'].default_value=color;bs.inputs['Roughness'].default_value=rough;return m
mats={n:material(n,c) for n,c in {'Outer_shell':s['color'],'Inner_carrier':(.052,.065,.075,1),'Soft_band':(.09,.10,.115,1),'Contact_pad':(.25,.27,.30,1),'Camera_case':(.018,.022,.027,1),'Lens_glass':(.015,.055,.08,1),'Cable_black':(.01,.012,.014,1),'Cable_signal':(.49,.19,.07,1),'Cable_speaker':(.10,.32,.48,1),'Fastener':(.28,.31,.34,1)}.items()}
def meshob(name,solid,mat='Inner_carrier',parent=None,coll=SC,kind='structure'):
 solid=union([t for t in solid.decompose() if t.volume()>1e-5])
 me=solid.to_mesh();v=np.asarray(me.vert_properties)[:,:3];f=np.asarray(me.tri_verts);data=bpy.data.meshes.new(name);data.from_pydata(v.tolist(),[],f.tolist());data.update();ob=bpy.data.objects.new(name,data);coll.objects.link(ob)
 if parent:ob.parent=parent
 ob.data.materials.append(mats[mat]);ob['export_physical']=True;ob['part_category']=kind;ob['volume_mm3']=solid.volume();ob['source_status']='parametric design estimate';return ob
def matrix(name):return np.array(bpy.data.objects[name].matrix_world)
cam=bpy.data.objects['MOVE__CS30'];cam.location=s['camera'];cam['pitch_deg']=-20.;cam.update_tag()
# Correct the old estimated camera port to the finished-case end face shown in the official drawing.
cp=bpy.data.objects['PORT__CS30_USB'];cp.location=(-44.97,2.5,-6.5);cp.rotation_euler=(0,-math.pi/2,0)
for ob in list(bpy.data.objects):
 if ob.name.startswith('Plug__CS30_USB'):bpy.data.objects.remove(ob,do_unlink=True)
meshob('Plug__CS30_USB_stub',box((6,10,6),(-47.97,2.5,-6.5)),'Cable_black',cam,SC,'component')
meshob('Plug__CS30_USB_elbow',box((6,10,12),(-49,2.5,-12.5)),'Cable_black',cam,SC,'component')
cl=bpy.data.objects['LEAD__CS30_USB'];cl.parent=cam;cl.location=(-49,2.5,-18.5);cl.rotation_euler=(math.pi,0,0)
for name in ['MOVE__Radxa_ZERO_3W','MOVE__MAX98357A','MOVE__INMP441','MOVE__USB_C_PWR_Splitter']:
 o=bpy.data.objects[name];o.location+=Vector(s['shift'])
 if KEY=='C':
  o.location.y*=.88
  if 'Splitter' in name:o.location.x-=4
 if 'MAX' in name:o.location.y-=18 if KEY=='C' else 12
 if 'INMP' in name:o.location.y+=15 if KEY=='C' else 8
 if 'Splitter' in name:
  o.location.y+=18 if KEY=='C' else 14
  if KEY=='C':o.location.x+=32;o.location.z-=18
 if KEY=='C':
  if 'Radxa' in name:o.location.x+=18
  if 'INMP' in name:o.location.x+=12
  if 'MAX' in name:o.location.x+=14
 if KEY=='B' and 'Splitter' in name:o.location.y+=7
 if KEY=='B' and 'Splitter' in name:o.location.x+=5
speaker=bpy.data.objects['MOVE__Speaker_27859'];speaker.location.x-=3
ph=bpy.data.objects['MOVE__Speaker_PH125_pair'];ph.location.x-=5
bat=bpy.data.objects['MOVE__Battery_NB10000_PLACEHOLDER'];bat.location=(0,-116,s['belt_z']-5)
update()

# Inner support surfaces and no-glue retention slots, in each component's own coordinate system.
mount_local={};mount_comments={}
rb=box((69,34,2),(0,0,-9.1))
# Ventilated rear mounting plate: edge rails remain continuous under the official mounting holes.
rb-=box((43,18,4),(0,0,-9.1))
holes=[(-28.950096,-11.400058),(28.899928,-11.400058),(28.899928,11.500074),(-28.900058,11.450036)]
for x,y in holes:rb+=cyl(3.3,6.48,(x,y,-8.1))-cyl(1.6,4.8,(x,y,-6.3))
mount_local['MOVE__Radxa_ZERO_3W']=rb
specs={'MOVE__INMP441':(14,14),'MOVE__MAX98357A':(19.4,17.8),'MOVE__USB_C_PWR_Splitter':(32,24)}
for name,(w,l) in specs.items():
 m=guide_tray(w,l,1.6,.3,1.6,2)
 if 'Splitter' in name:m=guide_tray(l,w,1.6,.3,1.6,2).rotate((0,0,90))
 if 'INMP' not in name:m-=box((w-7,l-7,5),(0,0,-3))
 cuts=[]
 for n,d in meta['objects'].items():
  if d['owner']==name and d['physical'] and not n.endswith('_PCB'):
   lo,hi=np.array(d['local_bounds']);cuts.append(box(hi-lo+.5,(lo+hi)/2))
 if cuts:m-=union(cuts)
 if 'INMP' in name:
  m-=cyl(1.5,10,(0,0,-7));m-=cyl(4,.6,(0,0,-1.7))-cyl(2,1,(0,0,-2))
 mount_local[name]=m
# Speaker front seat: the sound opening points toward the left ear.
sp=box((33.2,23.2,2),(0,0,4.7))-box((19,10,12),(0,0,7))
for sign in [-1,1]:
 for y in [-6,6]:sp+=box((1.6,5,9.5),(sign*16.1,y,.3))+box((3.1,5,1.6),(sign*15.35,y,-4.5))
mount_local['MOVE__Speaker_27859']=sp
mount_local['MOVE__Speaker_PH125_pair']=box((9,7,10))-box((5.6,3.6,13))-box((3.4,8,7),(0,3,0))
# A single moving camera/IMU carrier. Official external M3 spacing is 45mm; vertical slots allow the unlabelled datum.
cradle=box((62,14,2),(0,2.5,-15.6))
for x in [-22.5,22.5]:
 cradle+=box((8,13,2.1),(x,2.5,-13.55))
 cradle-=union([cyl(1.7,10,(x,y,-20)) for y in [-.5,5.5]]+[box((3.4,6,10),(x,2.5,-15))])
imu=bpy.data.objects['MOVE__ICM42688P_LogicalEdges'];imurel=np.array(cam.matrix_world.inverted()@imu.matrix_world)
it=guide_tray(25,18,1.6,.3,1.6,2)-box((18,11,5),(0,0,-3))
cradle+=tf(it,imurel)
cradle+=hull_between(box((4,7,3),(21,2.5,-15.6)),box((4,7,3),(21,2.5,-22)))
cradle+=hull_between(box((4,7,3),(21,2.5,-22)),tf(box((4,7,3),(-10,0,-3)),imurel))
for sign in [-1,1]:
 cradle+=hull_between(box((5,7,4),(sign*29,2.5,-15.6)),box((5,7,4),(sign*49,-9,-6)))
 cradle+=cyl(3.3,4,(sign*51,0,0),(sign,0,0))-cyl(1.7,6,(sign*50,0,0),(sign,0,0))
 cradle+=hull_between(box((5,5,4),(sign*49,-9,-6)),box((4,5,4),(sign*52,0,0)))

# Fit by moving devices outward only when the actual mount/backplate needs it.
def head_clear(v):
 out=[]
 for center,rs in [((0,0,0),(78,96,116)),((77,-15,-15),(8,17,27)),((-77,-15,-15),(8,17,27)),((0,92,-18),(12,20,23))]:
  q=v-np.array(center);r=np.linalg.norm(q/rs,axis=1);out.append((r-1)*min(rs))
 return np.min(out,axis=0)
def verts(solid):return np.asarray(solid.to_mesh().vert_properties)[:,:3]
for name,local in list(mount_local.items())+[('MOVE__CS30',cradle)]:
 o=bpy.data.objects[name];normal=np.array([o.location.x,o.location.y,0.]);normal/=np.linalg.norm(normal)
 # Camera goes forward; microphones remain flat; electronics orientation is inherited from v12.
 if name=='MOVE__CS30':normal=np.array([0.,1,0])
 for step in range(180):
  update();R=matrix(name);v=verts(local)@R[:3,:3].T+R[:3,3]
  if min(head_clear(v))>=1.2:break
  o.location+=Vector(normal*.2)
update()
roots={n:matrix(n) for n in meta['roots'] if n in bpy.data.objects}
poses={n:dict(translation_mm=(m[:3,3]-np.array(meta['roots'][n])[:3,3]).tolist(),matrix=m.tolist()) for n,m in roots.items()}

# Camera finished case reconstructed from the manufacturer's outer drawing, not a bare internal STEP box.
# 89.94 x 30 x 25, with a raised upper ridge, rounded ends, three optical apertures and rear M3 holes.
case=union([cyl(12.5,25,(-32.47,2.5,-12.5)),cyl(12.5,25,(32.47,2.5,-12.5)),box((64.94,25,25),(0,2.5,0)),box((60,5,25),(0,-12.5,0))])
for x in [-22,22]:case-=cyl(6.3,5,(x,2.5,9))
case-=box((5.5,6.5,5),(7,2.5,11.5))
for x in [-22.5,22.5]:case-=cyl(1.5,3,(x,2.5,-12.51))
case-=box((5,9,3.5),(-44.2,2.5,-6.5))
caseob=meshob('CS30_FINISHED_CASE__89p94x30x25',case,'Camera_case',cam,kind='component_case');caseob['source_status']='Reconstructed external shape from DFRobot manufacturer drawing; not an official exterior STEP.'
for x in [-22,22]:meshob('CS30_optical_face_'+str(x),cyl(5.7,.5,(x,2.5,11.1)),'Lens_glass',cam,HC,'component_optics')
meshob('CS30_IR_emitter_face',box((4.5,5.5,.5),(7,2.5,11.1)),'Lens_glass',cam,HC,'component_optics')
meshob('INNER__Camera_IMU_rigid_carriage',cradle,parent=cam)

# The carrier rail follows the head instead of crossing its interior.
railz={'A':34,'B':49,'C':83}[KEY]
cross=math.sqrt(1-(railz/116)**2);rx=78*cross+5;ry=96*cross+5
ts=np.linspace(-125,125,81)*math.pi/180
railpoints=np.array([[rx*math.sin(t),ry*math.cos(t),railz] for t in ts])
def poly_tube(points,r):return union([capsule(a,b,r) for a,b in zip(points[:-1],points[1:])])
carrier=poly_tube(railpoints,2.4)
mount_world={}
for name,local in mount_local.items():
 R=matrix(name);solid=tf(local,R);mount_world[name]=solid;carrier+=solid
 # Two legs joining real tray edges to the head-following rail, outside the head.
 lo,hi=solid.bounding_box()[:3],solid.bounding_box()[3:];mid=(np.array(lo)+np.array(hi))/2
 for dy in [-5,5]:
  sign=1 if dy>0 else -1
  if 'Radxa' in name:a=R[:3,3]+R[:3,0]*(sign*29)+R[:3,2]*-9.2
  elif 'MAX' in name:a=R[:3,3]+R[:3,0]*(sign*8.7)+R[:3,2]*-3.8
  elif 'Splitter' in name:a=R[:3,3]+R[:3,1]*(sign*11)+R[:3,2]*-3.8
  else:a=R[:3,3]+R[:3,0]*(sign*6)+R[:3,2]*-3.8
  if 'PH125' in name:a=R[:3,3]+R[:3,0]*4.6+R[:3,2]*dy/2
  if 'Speaker_27859' in name:a=R[:3,3]+R[:3,0]*(17 if dy>0 else -17)+R[:3,2]*4.7
  idx=np.argmin(np.linalg.norm(railpoints-a,axis=1));b=railpoints[idx]
  if 'Speaker_27859' in name:
   mid=a+[0,0,24];carrier+=capsule(a,mid,1.6)+capsule(mid,b,1.6)
  elif 'PH125' in name:
   mid=a+[0,0,15];carrier+=capsule(a,mid,1.6)+capsule(mid,b,1.6)
  else:carrier+=capsule(a,b,1.6)
# Fixed fork for the angle-adjustable camera cradle.
cc=np.array(cam.location)
for sign in [-1,1]:
 pivot=cc+np.array([sign*57,0,0]);fork=cyl(3.3,3,pivot,(-sign,0,0))-cyl(1.7,5,pivot+np.array([sign,0,0]),(-sign,0,0))
 anchor=railpoints[np.argmin(np.linalg.norm(railpoints-(pivot+[0,-22,-8]),axis=1))]
 carrier+=fork+capsule(pivot+[0,-3,0],pivot+[0,-20,-6],3)+capsule(pivot+[0,-20,-6],anchor,3)
 meshob('HARDWARE__Camera_pivot_M3_'+str(sign),cyl(1.45,10,pivot+np.array([sign*1.5,0,0]),(-sign,0,0))+cyl(2.8,2,pivot+np.array([sign*.5,0,0]),(sign,0,0)),'Fastener',coll=HC,kind='hardware')

# Distinct load-bearing geometries; these are not scaled copies.
if KEY=='A':
 outerhead=ellipsoid((83,101,121));innerhead=ellipsoid((81,99,119));region=box((220,170,80),(0,23,25.5))
 face=(outerhead-innerhead)^region
 notch=cyl(17,200,(0,-20,-11),(0,1,0))+box((34,200,50),(0,80,-36))
 face-=notch
 for sx in [-77,77]:face-=ellipsoid((9.5,18.5,28.5),(sx,-15,-15),96)
 carrier+=face
 # Wide brow/cheek contact pads fixed mechanically to the carrier.
 for z in [54,-8]:
  pts=[[79*math.sin(t),97*math.cos(t),z] for t in np.linspace(-.9,.9,35)]
  meshob('SOFT__Face_pad_'+str(z),poly_tube(pts,2.0),'Contact_pad',coll=HC,kind='soft')
 # A broad opaque wraparound visor, with a swept camera opening for every permitted angle.
 front=float(cam.location.y)+4;half=112
 def bez(a,b,c,d):
  t=np.linspace(0,1,41)[:,None];return (1-t)**3*np.array(a)+3*(1-t)**2*t*np.array(b)+3*(1-t)*t*t*np.array(c)+t**3*np.array(d)
 edge=np.vstack([bez((47,front),(75,front),(112,95),(112,46)),bez((112,46),(114,0),(106,-45),(93,-77))[1:]])
 poly=Polygon([[-x,y] for x,y in edge[::-1]]+edge.tolist())
 shell=extrude(list(poly.exterior.coords)[:-1],-17,69)-extrude(list(poly.buffer(-2).exterior.coords)[:-1],-15,67)-ellipsoid((85.5,103.5,123.5))-notch
 sweep=[]
 for tilt in np.linspace(0,20,41):
  R=np.eye(4);R[:3,:3]=np.array(Matrix.Rotation(math.radians(-90-tilt),3,'X'));R[:3,3]=cam.location
  sweep.append(tf(box((91.04,31.1,70),(0,0,15)),R))
 shell-=union(sweep)
 for ex in [-77,77]:shell-=ellipsoid((9.7,18.7,28.7),(ex,-15,-15),96)
 # Right heat slots.
 R=matrix('MOVE__Radxa_ZERO_3W')
 shell-=union([tf(box((3,24,80),(x,-3,30)),R) for x in np.arange(-25,26,5.5)])
 meshob('OUTER__Opaque_wraparound_visor',shell,'Outer_shell')
elif KEY=='B':
 # Two fully open eye rims, a nose bridge, and distinct ear hooks.
 for sign in [-1,1]:
  pts=[[sign*31+25*math.cos(t),111-abs(25*math.cos(t))*0.10,8+18*math.sin(t)] for t in np.linspace(0,2*math.pi,81)]
  rim=poly_tube(pts,2.2);carrier+=rim
  carrier+=poly_tube([(sign*55,109,20),(sign*72,65,20),(sign*80.5,25,20),(sign*80.5,25,49)],2.8)
  carrier+=capsule((sign*80.5,25,49),(sign*73,25,49),2.8)
  ax=81 if sign==1 else 90
  hook=[[sign*ax,-24,33],[sign*92,-38,25],[sign*92,-48,8],[sign*89,-53,5]]
  carrier+=poly_tube(hook,2.8)+capsule(hook[0],(sign*76,-15,49),2.8)
  meshob('SOFT__Nose_pad_'+str(sign),ellipsoid((3.5,3.2,7),(sign*14,107,0),48),'Contact_pad',coll=HC,kind='soft')
 carrier+=capsule((-8,111,15),(8,111,15),2.4)
elif KEY=='C':
 # A headphone-style crown yoke; the camera is suspended in front of the forehead, eyes left open.
 pts=[[88*math.sin(t),-12,18+112*math.cos(t)] for t in np.linspace(-math.pi/2,math.pi/2,101)]
 band=[]
 for a,b in zip(pts[:-1],pts[1:]):
  band.append(hull_between(box((3,23,3),a),box((3,23,3),b)))
 carrier+=union(band)
 for sign in [-1,1]:carrier+=capsule((sign*88,-12,48),(sign*74,-10,83),3.3)
 meshob('SOFT__Crown_pad',box((42,27,10),(0,-12,122)),'Contact_pad',coll=HC,kind='soft')
 for sign in [-1,1]:meshob('SOFT__Temple_pad_'+str(sign),ellipsoid((3,17,13),(sign*80,-12,41),48),'Contact_pad',coll=HC,kind='soft')

# Compact module covers for the two open designs. Every cover is cosmetic; retention is on the inner carrier.
if KEY!='A':
 for name in ['MOVE__Radxa_ZERO_3W','MOVE__MAX98357A','MOVE__USB_C_PWR_Splitter','MOVE__INMP441']:
  vals=[d['local_bounds'] for d in meta['objects'].values() if d['owner']==name and d['physical']];lo=np.min([v[0] for v in vals],0)-1.2;hi=np.max([v[1] for v in vals],0)+1.2
  depth0=-10.2 if 'Radxa' in name else -3.8
  lo[2]=depth0;size=hi-lo;center=(lo+hi)/2
  cover=box(size+4,center)-box(size,(lo+hi)/2)-box((size[0]+8,size[1]+8,10),(center[0],center[1],lo[2]-4))
  R=matrix(name)
  if 'Radxa' in name:cover-=union([box((3,22,30),(x,-3,15)) for x in np.arange(-25,26,5.5)])
  # Slots for cable egress, same directions as the retained plugs.
  for port in bpy.data.objects:
   if port.name.startswith('LEAD__'):
    par=port
    while par.parent and not par.name.startswith('MOVE__'):par=par.parent
    if par.name!=name:continue
    q=np.linalg.inv(R)@np.r_[np.array(port.matrix_world.translation),1];cover-=box((8,8,26),(q[0],q[1],q[2]+10))
  meshob('OUTER__'+name[6:]+'_cover',tf(cover,R),'Outer_shell')

# Independent rear battery cradle and elastic band. The battery is not a member of the mirror shell.
bz=float(bat.location.z);bp=box((121,2,51),(0,-106.8,bz))
for sign in [-1,1]:
 bp+=box((2,20,51),(sign*60,-116,bz))
 bp+=box((8,2,51),(sign*56,-126,bz))
 # Slots in raised tabs through which the rear elastic band is threaded.
 tab=box((12,5,35),(sign*46,-103,bz+5))-box((6,9,26),(sign*46,-103,bz+5));bp+=tab
bp+=box((121,20,2),(0,-116,bz-25))
# The two modeled USB-C outlets exit at the right end of this placeholder battery.
bp-=box((20,18,36),(61,-110,bz))
meshob('BATTERY__Independent_cradle',bp,'Inner_carrier')
# Actual straps curve around the rear of the head, with a flat rear section at the battery tray.
endz=s['belt_z'];strappts=[[-87,-55,endz],[-83,-75,endz],[-66,-103,endz],[-46,-104,endz],[0,-104,endz],[46,-104,endz],[66,-103,endz],[83,-75,endz],[87,-55,endz]]
strap=[]
for a,b in zip(strappts[:-1],strappts[1:]):strap.append(hull_between(box((2,2,25),a),box((2,2,25),b)))
meshob('SOFT__Rear_elastic_band_25mm',union(strap),'Soft_band',coll=HC,kind='soft')
for sign in [-1,1]:
 tab=box((7,10,33),(sign*87,-56,endz))-box((11,3.5,26),(sign*87,-57,endz))
 carrier+=tab
 idx=np.argmin(np.linalg.norm(railpoints-[sign*87,-55,endz],axis=1));carrier+=capsule((sign*87,-54,endz),railpoints[idx],3)
# Explicit device reliefs apply to the supporting rails, never to the retaining trays/posts.
clearance=[]
for n,d in meta['objects'].items():
 if not d['physical'] or d['owner'] not in mount_world or d['owner'].startswith('MOVE__OPTION'):continue
 lo,hi=np.array(d['local_bounds']);clearance.append(tf(box(hi-lo+.5,(hi+lo)/2),matrix(d['owner'])))
mount_union=union(mount_world.values())
carrier=(carrier-mount_union-union(clearance))+mount_union
carrier=union([t for t in carrier.decompose() if t.volume()>1e-5])
print('CARRIER CONNECTED PARTS',len(carrier.decompose()),flush=True)
json.dump([dict(volume=t.volume(),bounds=t.bounding_box()) for t in carrier.decompose()],open(DEST/'carrier_connectivity.json','w'),indent=2)
meshob('INNER__Main_load_carrier',carrier)

# Keep the v12 battery placeholder. Duplicate only the second connector/port clearance on the same power bank.
orig_port=bpy.data.objects.get('PORT__Battery_C');orig_lead=bpy.data.objects.get('LEAD__Battery_C')
if orig_port:
 # Move the original output to the lower outlet, then copy its already modeled plug to the upper outlet.
 orig_port.location.z=-8
 update()
 second=orig_port.copy();second.name='PORT__Battery_C_2';second.parent=bat;SC.objects.link(second);second.location=orig_port.location.copy();second.location.z=8
 for child in list(orig_port.children_recursive):
  if child.type=='MESH':
   cp=child.copy();cp.data=child.data.copy();cp.name=child.name+'_output2';SC.objects.link(cp);cp.parent=second;cp.matrix_local=child.matrix_local.copy()
 lead=bpy.data.objects.new('LEAD__Battery_C_2',None);SC.objects.link(lead);lead.parent=second
 if orig_lead:lead.matrix_local=orig_lead.matrix_local.copy()
update()

# Export routing inputs, all retained endpoint positions and their exit directions.
leads={}
for ob in bpy.data.objects:
 if ob.name.startswith(('LEAD__','PORT__','QWIRE_END_','SPEAKER_','PH125_','AMP_OUTPUT_')) and ob.type=='EMPTY':
  par=ob
  while par.parent and not par.name.startswith('MOVE__'):par=par.parent
  leads[ob.name]=dict(point=list(ob.matrix_world.translation),direction=list(ob.matrix_world.to_3x3()@Vector((0,0,1))),owner=par.name)
cam['pitch_deg']=-20.;cam.update_tag();update()
settings=dict(key=KEY,style=s,poses=poses,leads=leads,camera_center=list(cam.location),wire_radius_usb=1.5,wire_min_radius_usb=12.,wire_radius_signal=.4,wire_min_radius_signal=3.2,wire_radius_speaker=.6,wire_min_radius_speaker=4.8,band_stretch_allowance=20.,bend_rule='Geometric design criteria: USB 4D, individual signal/speaker conductors 4D. Cable supplier limits are not yet known. These are not manufacturer-qualified cable limits.')
json.dump(settings,open(DEST/'design_data.json','w',encoding='utf-8'),indent=2,ensure_ascii=False)
# All named physical mesh data are passed to the independent collision/routing stage.
update();dg=bpy.context.evaluated_depsgraph_get();obdata={};arrays={}
for ob in bpy.data.objects:
 if ob.type!='MESH' or not(ob.get('export_physical') or ob.name in ['REF_head','REF_ear_L','REF_ear_R','REF_nose']):continue
 eo=ob.evaluated_get(dg);me=eo.to_mesh();me.calc_loop_triangles();v=np.array([eo.matrix_world@q.co for q in me.vertices]);f=np.array([t.vertices[:] for t in me.loop_triangles]);eo.to_mesh_clear()
 if not len(v):continue
 owner=ob
 while owner.parent and not owner.name.startswith('MOVE__'):owner=owner.parent
 obdata[ob.name]=dict(owner=owner.name,category=ob.get('part_category','component'),bounds=[v.min(0).tolist(),v.max(0).tolist()]);arrays[ob.name+'__v']=v;arrays[ob.name+'__f']=f
np.savez_compressed(DEST/'working_meshes.npz',**arrays);json.dump(obdata,open(DEST/'working_objects.json','w'),indent=2)
bpy.ops.wm.save_as_mainfile(filepath=str(DEST/'working.blend'))
print('BUILT',KEY,s['name'].encode('ascii','backslashreplace').decode(),len(obdata),flush=True)
