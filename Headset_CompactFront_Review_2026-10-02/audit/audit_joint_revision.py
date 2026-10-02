from pathlib import Path
import json,hashlib,math
import numpy as np
import manifold3d as md
P=Path(__file__).resolve().parent;ROOT=P.parents[1];G=P.parent/'geometry';R=ROOT/'Headset_Carbon6K_FlatBase_Review_2026-10-02/geometry';M=md.Manifold
def load(p):
 a=np.load(p);return M(md.Mesh64(vert_properties=np.ascontiguousarray(a['v'],dtype=np.float64),tri_verts=np.ascontiguousarray(a['f'],dtype=np.uint64)))
def vol(a,b):return max(0,float((a^b).volume()))
def box(a,b):return M.cube(tuple(np.array(b)-a)).translate(tuple(a))
front=load(G/'front_unified_preview.npz');rear=load(R/'rear_unified_preview.npz');fg=json.loads((G/'geometry_values.json').read_text());rg=json.loads((R/'geometry_values.json').read_text());camera=load(G/'camera.npz');battery=load(R/'battery_preview.npz')
report={'front_source_sha256':hashlib.sha256((G/'front_unified_preview.npz').read_bytes()).hexdigest(),'rear_source_sha256':hashlib.sha256((R/'rear_unified_preview.npz').read_bytes()).hexdigest(),'front_rear_intersection_mm3':vol(front,rear),'rear_band_intersection_mm3':vol(rear,load(R/'straps_preview.npz')),'installed_camera_mm3':vol(front,camera),'battery_installed_mm3':vol(rear,battery),'front_spring_sweep_other_material_mm3':vol(load(G/'spring_deflection_sweep.npz'),load(G/'front_without_springs.npz')),'rear_spring_sweep_other_material_mm3':vol(load(R/'rear_spring_motion.npz'),load(R/'rear_without_springs.npz')),'optical_field_intersection_mm3':fg['optical_cone_shell_intersection_mm3'],'negative_front_air_boundary_count':sum(a.volume()<-1e-6 for a in front.decompose()),'front_volume_cm3':front.volume()/1000,'rear_volume_cm3':rear.volume()/1000,'rear_bounds':list(rear.bounding_box())}
# Verify hook capture under the FULL0.6 lateral float, not just centered fit.
report['rear_capture_mm']=rg['spring']['hook_inward_projection_mm']-(23.4-22.8)
report['rear_strain']=3*1*1.4/(2*12**2)
radius=11.4/math.cos(math.pi/384);move=29.701
bp=M.cylinder(90.4,radius,circular_segments=384).transform([[0,0,1,-45.2],[1,0,0,217],[0,1,0,39.2]])
sweep=M.batch_hull([bp,bp.translate((0,0,move))])
report['battery_upward_path_no_hooks_mm3']=vol(sweep,load(R/'rear_without_hook.npz'))
report['battery_upward_path_front_mm3']=vol(sweep,front)
report['rear_fully_exited_battery_min_z_mm']=27.8+move
# Inspect full-width retained front band at24.34.
report['remaining_original_above_flat_band_cut_mm3']=vol(load(G/'original_modified.npz'),box([-45.3,-50,24.340001],[45.3,30,100]))
report['front_top_horizontal_faces']={}
a=np.load(G/'front_unified_preview.npz');tri=a['v'][a['f']];n=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);keep=(n[:,2]>1e-10)&(np.ptp(tri[:,:,2],axis=1)<1e-6)
tops=tri[keep].mean(1)
# Report remaining horizontal ledges separately; a global coplanar-contact
# top does not imply every hook/notch/retained original ledge is57.14.
report['horizontal_up_faces_below_top_examples_xyz']=tops[tops[:,2]<57.1399][:12].tolist()
report['front_new_nominal_plates_mm']={'camera_front':2,'camera_side':2,'camera_bottom':2,'flat_top':2,'chamfer':2,'raised_rim_height':2.02,'spring':1}
(P/'joint_revision_checks.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report,indent=2))
