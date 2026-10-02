from pathlib import Path
import json,math,hashlib
import numpy as np
import manifold3d as md
P=Path(__file__).resolve().parent;G=P.parent/'geometry';M=md.Manifold
def load(n):
 a=np.load(G/(n+'.npz'));return M(md.Mesh64(vert_properties=np.ascontiguousarray(a['v'],dtype=np.float64),tri_verts=np.ascontiguousarray(a['f'],dtype=np.uint64)))
def box(lo,hi):
 lo=np.array(lo,float);hi=np.array(hi,float);return M.cube(tuple(hi-lo)).translate(tuple(lo))
def save(n,m):
 a=m.to_mesh64();np.savez_compressed(G/(n+'.npz'),v=np.array(a.vert_properties)[:,:3],f=np.array(a.tri_verts))
r=json.loads((G/'geometry_values.json').read_text());PY,PZ=r['pivot_yz_mm'];T=np.array(r['camera_transform'])
front=load('front_unified_preview');original=load('original');modified=load('original_modified');shell=load('new_shell');hooks=load('hooks')
solid=front-hooks
horiz=box([-44.97,PY-25,PZ],[44.97,200,PZ+30])
pts=[]
for theta in np.linspace(0,20,401):
 a=math.radians(theta);c,s=math.cos(a),math.sin(a)
 for h in [0,30]:
  for t in [0,25]:pts.append([PY-c*t-s*h,PZ-s*t+c*h])
rot=md.CrossSection.hull_points(np.array(pts)).offset(.00001).extrude(89.94).transform([[0,0,1,-44.97],[1,0,0,0],[0,1,0,0]])
# Analytic support bounds of the continuous rectangle motion clip the tiny
# circumscription outside the final front/bottom contact planes.
rot=rot^box([-100,0,-200],[100,200,25]).transform(T)
above=box([-200,-2.5,-250],[200,200,250]).transform(T)
below=box([-200,-250,-250],[200,-2.5,250]).transform(T)
test={'geometry_sha256':hashlib.sha256((G/'front_unified_preview.npz').read_bytes()).hexdigest(),'horizontal_sweep_intersection_excluding_hooks_mm3':abs((horiz^solid).volume()),'horizontal_original_only_collision_mm3':abs((horiz^modified).volume()),'horizontal_new_shell_collision_mm3':abs((horiz^(shell-hooks)).volume()),'rotation_conservative_envelope_intersection_excluding_hooks_mm3':abs((rot^solid).volume()),'installed_camera_collision_excluding_hooks_mm3':abs((load('camera')^solid).volume()),'original_below_outer_bottom_plane_changed_mm3':abs(((original-modified)^below).volume()),'new_camera_region_material_below_outer_bottom_plane_mm3':r['below_floor_added_camera_region_mm3'],'fixed_wing_bounds':{},'flat_pose_at_stop_camera_intersection_mm3':abs((load('camera_flat')^solid).volume()),'individual_insertion_poses':[]}
coll=horiz^solid;save('horizontal_collision',coll)
flat=load('camera_flat')
for d in [0,1,3,5,10,20,30,40]:
 camera=flat.translate((0,d,0));intersection=camera^solid
 test['individual_insertion_poses'].append({'rearward_offset_from_stop_mm':d,'collision_mm3':abs(intersection.volume())})
 if d==10:save('insertion_witness_camera',camera);save('insertion_witness_collision',intersection)
for s in ['left','right']:
 wing=load('wing_'+s);test['fixed_wing_bounds'][s]=list(wing.bounding_box())
save('horizontal_actual_sweep',horiz);save('rotation_actual_sweep_conservative',rot)
test['horizontal_blocking_original_bounds_xyz_mm']=list(coll.bounding_box())
test['minimum_original_material_removal_for_exact_horizontal_path_mm3']=abs((horiz^modified).volume())
test['rotation_envelope_method']='Convex hull of all four corner samples every0.05deg plus0.00001mm offset; corner chord sagitta <=0.00000372mm. Conservative covers continuous20deg sweep but may include non-swept inner areas.'
test['shell_plates_nominal_mm']={'front':2,'bottom':2,'side':2,'flat_top':2,'chamfer':2}
test['preserved_ears_thickness_mm']=[3.2590459,3.4156225]
test['minimum_inside_flat_top_gap_mm']=55.14-(PZ+30)
test['front_overall_max_forward_mm']=-front.bounding_box()[1]
test['central_region_max_forward_mm']=-load('central_shell').bounding_box()[1]
(P/'solid_checks.json').write_text(json.dumps(test,indent=2),encoding='utf8')
print(json.dumps(test,indent=2))
