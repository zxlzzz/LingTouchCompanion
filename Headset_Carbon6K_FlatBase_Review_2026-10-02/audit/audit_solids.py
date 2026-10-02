"""Exact solid checks and conservative continuous vertical battery sweep."""
from pathlib import Path
import json,hashlib,math
import numpy as np
import manifold3d as md
P=Path(__file__).resolve().parent;G=P.parent/'geometry';ROOT=P.parents[1];M=md.Manifold
FRONT=ROOT/'Headset_CompactFront_Review_2026-10-02/geometry/front_unified_preview.npz'
def load(path):
 a=np.load(path);return M(md.Mesh64(vert_properties=np.ascontiguousarray(a['v'],dtype=np.float64),tri_verts=np.ascontiguousarray(a['f'],dtype=np.uint64)))
def coll(a,b):return max(0,float((a^b).volume()))
g=json.loads((G/'geometry_values.json').read_text());rear=load(G/'rear_unified_preview.npz');no=load(G/'rear_without_hook.npz');battery=load(G/'battery_preview.npz');front=load(FRONT);straps=load(G/'straps_preview.npz')
r=11.4/math.cos(math.pi/384);distance=27.401
poly=M.cylinder(90.4,r,circular_segments=384).transform([[0,0,1,-45.2],[1,0,0,217],[0,1,0,39.2]])
sweep=M.batch_hull([poly,poly.translate((0,0,distance))])
a=sweep.to_mesh64();np.savez_compressed(G/'battery_vertical_sweep.npz',v=np.array(a.vert_properties)[:,:3],f=np.array(a.tri_verts))
v=np.load(G/'rear_unified_preview.npz')['v']
report={'rear_source_sha256':hashlib.sha256((G/'rear_unified_preview.npz').read_bytes()).hexdigest(),'front_source_sha256':hashlib.sha256(FRONT.read_bytes()).hexdigest(),'single_connected_closed_solid':len(rear.decompose())==1,'overall_xyz_dimensions_mm':(v.max(0)-v.min(0)).tolist(),'volume_cm3':rear.volume()/1000,'rear_front_intersection_mm3':coll(rear,front),'rear_straps_intersection_mm3':coll(rear,straps),'battery_installed_nohook_intersection_mm3':coll(battery,no),'battery_installed_withhook_intersection_mm3':coll(battery,rear),'battery_vertical_path_nohook_intersection_mm3':coll(sweep,no),'battery_vertical_path_straps_intersection_mm3':coll(sweep,straps),'battery_vertical_path_front_intersection_mm3':coll(sweep,front),'battery_vertical_path_hook_intersection_mm3':coll(sweep,load(G/'rear_hook.npz')),'vertical_sweep':{'translation_z_mm':distance,'radius_circumscribed_mm':r,'segments':384,'fully_clear_battery_min_z_mm':27.8+distance,'method':'Convex hull of an enclosing384-sided circular cylinder at both ends of+Z motion equals its continuous vertical translate union. Zero non-hook intersection covers the true circular cylinder, not sampled steps.'},'spring':{'free_upward_play_before_nominal_circle_hook_contact_mm':42.8-39.2-math.sqrt(11.4**2-(227.9-217)**2),'required_maximum_geometric_deflection_y_mm':228.4-227.9,'physical_deflection':'Not tested'},'box_inner_clearance_each_side_mm':.3,'mouth_xy_mm':[91,23.4],'strap_lengths_mm':[g['strap_paths'][s]['free_length_mm'] for s in ['left','right']]}
assert report['battery_vertical_path_nohook_intersection_mm3']<1e-6 and report['battery_vertical_path_straps_intersection_mm3']<1e-6 and report['rear_front_intersection_mm3']<1e-6
(P/'solid_collision_audit.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report,indent=2))
