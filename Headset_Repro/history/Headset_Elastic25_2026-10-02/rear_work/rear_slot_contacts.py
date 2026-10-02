from pathlib import Path
import json,numpy as np
from rear_surface import offset_rear_points
P=Path(__file__).resolve().parent
rows=[]
for side in [-1,1]:
    for z in [26.2,26.7,39.2,51.7,52.2]:
        center=np.array([side*66.8,z]);mid,mn,mi,me=offset_rear_points([center],2.25)
        outer,on,oi,oe=offset_rear_points([center],3.5)
        # Width3 along outer horizontal curve: front edge at arc+1.5 outward.
        lo,hi=0.,3.
        for _ in range(22):
            dx=(lo+hi)/2
            queries=np.column_stack([side*(66.8+np.linspace(0,dx,13)),np.full(13,z)])
            curve,_,_,err=offset_rear_points(queries,3.5)
            length=np.linalg.norm(np.diff(curve,axis=0),axis=1).sum()
            if length<1.5:lo=dx
            else:hi=dx
        contact,cn,ci,ce=offset_rear_points([[side*(66.8+hi),z]],3.5)
        rows.append({'side':'left' if side<0 else 'right','z_mm':z,'slot_mid_surface_center_xyz_mm':mid[0].tolist(),'slot_mid_normal':mn[0].tolist(),'slot_outer_center_xyz_mm':outer[0].tolist(),'slot_outer_normal':on[0].tolist(),'free_band_outer_front_edge_contact_xyz_mm':contact[0].tolist(),'contact_outer_normal':cn[0].tolist(),'front_edge_arc_from_center_mm':1.5,'front_edge_delta_abs_x_mm':hi,'offset_solver_residual_mm':float(ce[0]),'scope':'Exact original-head triangle-distance level3.5mm. Reference slot front edge at horizontal outer-surface arc1.5mm from center; final Boolean tangent-cut slot may have a slightly different edge and must be queried from unified mesh. Continuous tray validation in rear_actual_clearance.json.'})
(P/'rear_slot_contacts.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
print(json.dumps(rows,indent=2))
