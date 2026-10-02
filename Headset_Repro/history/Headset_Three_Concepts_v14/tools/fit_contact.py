"""Set actual soft contact geometry and connect the spectacle nose / ear rests to its inner carrier."""
import bpy,sys,json,numpy as np,os
from pathlib import Path
from mathutils import Vector
from mathutils.bvhtree import BVHTree
from cad_kernel import *
P=Path(__file__).parent.parent;K=sys.argv[1];D=P/K
bpy.ops.wm.open_mainfile(filepath=str(D/('Concept_'+K+'.blend')),load_ui=False,use_scripts=False);bpy.context.preferences.filepaths.save_version=0
coll=bpy.data.collections['11_Hardware_and_Soft_Parts'];base=bpy.data.objects['INNER__Main_load_carrier']
def put(ob,s):
 m=s.to_mesh();me=bpy.data.meshes.new(ob.name);me.from_pydata(np.asarray(m.vert_properties)[:,:3].tolist(),[],np.asarray(m.tri_verts).tolist());me.update();mats=list(ob.data.materials);ob.data=me
 for mat in mats:ob.data.materials.append(mat)
 ob['volume_mm3']=s.volume();return ob
def add(name,s):
 ob=bpy.data.objects.get(name)
 if ob is None:
  ob=bpy.data.objects.new(name,bpy.data.meshes.new(name));coll.objects.link(ob);ob.data.materials.append(bpy.data.materials['Contact_pad'])
 put(ob,s);ob['export_physical']=True;ob['part_category']='soft';return ob
def solid(ob):
 ob.data.calc_loop_triangles();v=np.array([ob.matrix_world@p.co for p in ob.data.vertices],np.float32);f=np.array([t.vertices[:] for t in ob.data.loop_triangles],np.uint32);return M(md.Mesh(v,f))
if K=='A':
 for ob in list(bpy.data.objects):
  if ob.name.startswith('SOFT__Face_pad_'):bpy.data.objects.remove(ob,do_unlink=True)
 for z in [54,-8]:
  intervals=[(-.9,.9)] if z>0 else [(-.9,-.27),(.27,.9)]
  for j,(a,b) in enumerate(intervals):
   pts=[]
   for t in np.linspace(a,b,45):
    fact=np.sqrt(1-(z/119)**2);p=np.array([81*fact*np.sin(t),99*fact*np.cos(t),z]);normal=np.array([p[0]/81**2,p[1]/99**2,0.]);normal/=np.linalg.norm(normal);pts.append(p-normal*1.7)
   add('SOFT__Face_pad_'+str(z)+'_'+str(j),union([capsule(a,b,2) for a,b in zip(pts[:-1],pts[1:])]))
elif K=='B':
 parts=[]
 for sign in [-1,1]:
  add('SOFT__Nose_pad_'+str(sign),ellipsoid((3.5,3.2,7),(sign*8,108,-8),48))
  parts += [capsule((sign*8,111,15),(sign*8,109,-4),1.6)]
  add('SOFT__Ear_rest_'+str(sign),ellipsoid((5,12,3.5),(sign*78,-15,14.5),48))
  parts += [capsule((sign*79,-26,19),(sign*79,-4,19),1.8)]
  if sign==1:parts += [capsule((80.5,25,49),(79,-12,19),1.8)]
  else:parts += [capsule((-90,-24,33),(-79,-24,35),1.8),capsule((-79,-24,35),(-79,-14,19),1.8)]
 put(base,solid(base)+union(parts))
elif K=='C':
 add('SOFT__Crown_pad',box((42,27,13.5),(0,-12,121.75)))
 for sign in [-1,1]:add('SOFT__Temple_pad_'+str(sign),ellipsoid((7.5,17,13),(sign*78,-12,41),48))
# An actual two-wall elastic sleeve retains both service loops. Its ends are open at the two independent clamps.
routes=json.loads((D/'routes.json').read_text());a,b=np.array(routes['POWER_1']['clamps']);a2,b2=np.array(routes['POWER_2']['clamps']);u=(b-a)/np.linalg.norm(b-a);v=np.array([0.,0.,1.]);normal=np.cross(u,v);T=np.eye(4);T[:3,:3]=np.column_stack([u,normal,v]);T[:3,3]=(a+b+a2+b2)/4
for ob in list(bpy.data.objects):
 if ob.name.endswith('_stretch_sleeve'):bpy.data.objects.remove(ob,do_unlink=True)
sleeve=tf(box((88,5.2,65))-box((90,4,63.8)),T);ob=add('SOFT__Twin_power_stretch_sleeve',sleeve);ob.data.materials.clear();ob.data.materials.append(bpy.data.materials['Soft_band'])
bpy.context.view_layer.update();checks=[]
def tree(ob):
 ob.data.calc_loop_triangles();v=[ob.matrix_world@p.co for p in ob.data.vertices];f=[t.vertices[:] for t in ob.data.loop_triangles];return BVHTree.FromPolygons(v,f,all_triangles=True)
headtrees=[tree(bpy.data.objects[n]) for n in ['REF_head','REF_ear_L','REF_ear_R','REF_nose']];carrier=tree(base)
for ob in coll.objects:
 if not ob.name.startswith(('SOFT__Face_pad_','SOFT__Nose_pad_','SOFT__Ear_rest_','SOFT__Crown_pad','SOFT__Temple_pad_')):continue
 tr=tree(ob);touchhead=any(tr.overlap(h) for h in headtrees);touchbase=bool(tr.overlap(carrier));checks.append(dict(pad=ob.name,intersects_reference_head=touchhead,intersects_carrier=touchbase))
(D/'contact_checks.json').write_text(json.dumps(checks,indent=2));print('CONTACTS',K,checks,flush=True)
bpy.ops.wm.save_as_mainfile(filepath=str(D/'contact_fitted.blend'));os.replace(D/'contact_fitted.blend',D/('Concept_'+K+'.blend'))
