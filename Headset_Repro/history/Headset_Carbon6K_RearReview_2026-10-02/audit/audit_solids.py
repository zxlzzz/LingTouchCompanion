"""Read-only manifold collision, swept battery and thickness review."""
from pathlib import Path
import json,hashlib
import numpy as np
import manifold3d as md
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1];G=HERE.parent/'geometry';M=md.Manifold
FRONT=ROOT/'Headset_ThinShell_Review_2026-10-02/geometry/front_unified_preview.npz'

def load(p):
    a=np.load(p);m=M(md.Mesh64(vert_properties=np.ascontiguousarray(a['v'],dtype=np.float64),tri_verts=np.ascontiguousarray(a['f'],dtype=np.uint64)))
    assert m.status()==md.Error.NoError,(p,m.status())
    return m
def intersection(a,b):
    m=a^b;return {'volume_mm3':float(m.volume()),'components':len(m.decompose()),'mesh_status':str(m.status())}
def cylinder_x(length,r,x0,y0,z0,segments=384):
    return M.cylinder(length,r,circular_segments=segments).transform([[0,0,1,x0],[1,0,0,y0],[0,1,0,z0]])
def main():
    rear=load(G/'rear_unified_preview.npz');rno=load(G/'rear_without_hook.npz');front=load(FRONT);fullstrap=load(G/'straps_preview.npz');free=load(G/'free_straps.npz');battery=load(G/'battery_preview.npz')
    a=np.load(G/'rear_unified_preview.npz');v=a['v'];values=json.loads((G/'geometry_values.json').read_text(encoding='utf-8'));ends=np.array(values['battery_axis_endpoints_mm']);x0=ends[0,0];x1=ends[1,0];y,z=ends[0,1:]
    distance=values['box_dimensions_mm']['open_x']-x0+.001
    # Circumscribed polygon strictly contains the exact circular cylinder;
    # one continuous axial prism is the complete translate-union, not samples.
    radius=11.4/np.cos(np.pi/384)
    sweep=cylinder_x(x1-x0+distance,radius,x0,y,z)
    result={'rear_source_sha256':hashlib.sha256((G/'rear_unified_preview.npz').read_bytes()).hexdigest(),'front_source_sha256':hashlib.sha256(FRONT.read_bytes()).hexdigest(),'one_closed_connected_print_piece':len(rear.decompose())==1,'rear_mesh_status':str(rear.status()),'overall_xyz_dimensions_mm':(v.max(0)-v.min(0)).tolist(),'bounds_xyz_mm':[v.min(0).tolist(),v.max(0).tolist()],'volume_mm3':float(rear.volume()),'rear_front_intersection':intersection(rear,front),'free_straps_rear_intersection':intersection(free,rear),'full_straps_rear_intersection':intersection(fullstrap,rear),'free_straps_front_intersection':intersection(free,front),'battery_rear_without_hook_intersection':intersection(battery,rno),'battery_rear_with_hook_intersection':intersection(battery,rear),'battery_full_exit_sweep_without_hook':intersection(sweep,rno),'battery_full_exit_sweep_with_straps':intersection(sweep,fullstrap),'battery_full_exit_sweep_against_front':intersection(sweep,front),'battery_sweep_definition':{'circular_radius_mm':11.4,'conservative_polygon_radius_mm':float(radius),'polygon_segments':384,'initial_x_interval_mm':[float(x0),float(x1)],'translation_mm':float(distance),'swept_x_interval_mm':[float(x0),float(x1+distance)],'method':'Continuous Minkowski translate union along +X. A circumscribed polygon contains the full true circular cylinder, making zero intersection a conservative exact-shape path certificate.'},'strap_paths':values['strap_paths'],'physical_spring_deflection_and_actual_battery_port_geometry':'没查'}
    result['rear_front_bbox_separation_y_mm']=float(v[:,1].min()-np.load(FRONT)['v'][:,1].max())
    (HERE/'solid_collision_audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))
if __name__=='__main__':main()
