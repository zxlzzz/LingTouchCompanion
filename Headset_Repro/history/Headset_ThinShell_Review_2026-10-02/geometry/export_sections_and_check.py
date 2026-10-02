"""Read-only solid checks and section-half meshes for inspection rendering."""
from pathlib import Path
import json,math
import numpy as np
import manifold3d as md
P=Path(__file__).resolve().parent;M=md.Manifold
def load(name):
 a=np.load(P/(name+'.npz'));return M(md.Mesh64(vert_properties=np.ascontiguousarray(a['v'],dtype=np.float64),tri_verts=np.ascontiguousarray(a['f'],dtype=np.uint64)))
def save(name,m):
 a=m.to_mesh64();v=np.array(a.vert_properties)[:,:3];f=np.array(a.tri_verts)
 np.savez_compressed(P/(name+'.npz'),v=v,f=f)
def box(lo,hi):
 lo=np.array(lo,float);hi=np.array(hi,float);return M.cube(tuple(hi-lo)).translate(tuple(lo))
report={}
for cut in [0,30]:
 cutter=box([cut,-250,-50],[200,350,150])
 for source,label in [('original_modified','original'),('new_shell','shell'),('camera','camera')]:
  m=load(source)^cutter;assert m.status()==md.Error.NoError
  save('section'+str(cut)+'_'+label,m)
front=load('front_unified_preview');hooks=load('hooks');camera=load('camera');cut=load('camera_entry_sweep_cut')
nominal_camera_coll=front^camera
C=math.cos(math.radians(20));S=math.sin(math.radians(20))
T=np.array([[1,0,0,0],[0,-S,-C,-.8],[0,C,-S,23.6]])
sweep=box([-44.97,0,-200],[44.97,30,25]).transform(T)
pathcoll=sweep^(front-hooks)
report['camera_actual_pose_intersection_mm3']=abs(float(nominal_camera_coll.volume()))
report['complete_axial_retreat_sweep_intersection_excluding_hooks_mm3']=abs(float(pathcoll.volume()))
save('camera_retreat_sweep',sweep)
if not pathcoll.is_empty():save('camera_retreat_collision',pathcoll)
original=load('original');modified=load('original_modified')
expected=original-cut
ab=modified-expected;ba=expected-modified
report['original_modification_vs_only_entry_cut_symmetric_difference_mm3']=abs(float(ab.volume()))+abs(float(ba.volume()))
report['original_only_removed_volume_mm3']=float((original-modified).volume())
report['new_shell_volume_mm3']=float(load('new_shell').volume())
report['body_new_wall_nominal_mm']={'side':2,'top_camera_normal':2,'bottom_camera_normal':2,'front_camera_axis':2,'floor_vertical':2,'under_nose_side':2}
report['wing_corresponding_front_surface_offsets_mm']={}
for side in ['left','right']:
 a=np.load(P/f'wing_{side}_front_corresponding_surfaces.npz');delta=a['inner']-a['outer'];length=np.linalg.norm(delta,axis=2)
 report['wing_corresponding_front_surface_offsets_mm'][side]={'min':float(length.min()),'max':float(length.max()),'nominal_top_plate_vertical':2,'nominal_bottom_plate_normal':2}
report['whole_joined_shell_global_thickness']='Not established by corresponding surface offsets; edge/junction sampling is separate.'
(P/'readonly_geometry_checks.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report,indent=2))
