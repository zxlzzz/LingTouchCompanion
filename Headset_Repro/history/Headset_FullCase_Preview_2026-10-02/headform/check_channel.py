"""Continuous nasal triangle witness against the new X=+/-13 channel walls."""
from pathlib import Path
import json,numpy as np
P=Path(__file__).resolve().parent;R=P.parents[1]
source=R/'Headset_TwoParts_Preview_2026-10-02/headform'
q=np.load(source/'Medium_Trial_Registered.npz');V,F=q['v'],q['f']
np.savez_compressed(P/'Medium_Trial_Registered.npz',v=V,f=F)
old_registration=json.loads((source/'head_registration_new.json').read_text())
registration={k:old_registration[k] for k in ['headform','scale','native_units','source_url','native_to_current_matrix','seating_status','registration_method','notch_apex_current_xyz_mm','nose_bridge_native_xyz_mm','nose_bridge_current_xyz_mm','ear_native_xyz_mm','ear_current_xyz_mm','ear_contact_target_leg_bottom_z_mm','limits']}
registration['new_case_status']='Unchanged trial head pose; current actual new-case distance record is actual_case_nose_distance.json. Old socket distances are not carried into this revision.'
(P/'head_registration_trial.json').write_text(json.dumps(registration,indent=2),encoding='utf-8')
np.savez_compressed(P/'nose_center_section.npz',**dict(np.load(source/'nose_center_section.npz')))
angle=np.deg2rad(20);UP=np.array([0,-np.sin(angle),np.cos(angle)]);FW=np.array([0,-np.cos(angle),-np.sin(angle)]);O=np.array([0,-.8,23.6])
# Halfspaces n dot p <= d define YZ polygon on the channel wall.
planes=[(np.array([0,1,0.]),0.),(np.array([0,0,-1.]),0.),(UP,-2.5+UP@O),(FW,25+FW@O)]
def clip(poly,n,d):
    out=[]
    if not len(poly):return []
    a=poly[-1];sa=a@n-d
    for b in poly:
        sb=b@n-d
        if (sa<=0)!=(sb<=0):out.append(a+(b-a)*(sa/(sa-sb)))
        if sb<=0:out.append(b)
        a,sa=b,sb
    return out
tri=V[F]
sel=(np.abs(tri[:,:,0]).min(1)<20)&(tri[:,:,1].min(1)<1)&(tri[:,:,2].max(1)>0)&(tri[:,:,2].min(1)<25)
best=None
for i in np.flatnonzero(sel):
    poly=list(tri[i])
    for n,d in planes:poly=clip(poly,n,d)
    if not len(poly):continue
    for point in poly:
        if abs(point[0])>13:continue
        delta=13-abs(point[0])
        if best is None or delta<best[0]:best=(float(delta),point,int(i))
wall=best[1].copy();wall[0]=13*np.sign(wall[0])
report={'head_pose':'Same unscaled Medium trial seating; full original BTTF wearing remains unverified/blocked by leg overlap.',
 'scope':'New material at Y<0 only; original BTTF not measured.',
 'assumed_channel_wall':'X=+/-13, q<=-2.5, Z>=0, Y<=0, t<=25. Side of removed through nose channel. Camera origin (0,-.8,23.6), tilt20deg.',
 'continuous_nose_to_channel_wall_witness_mm':best[0],'nose_witness_xyz_mm':best[1].tolist(),'case_witness_xyz_mm':wall.tolist(),'head_face_index':best[2],
 'strict_Y_negative_note':'If witness Y=0, the same distance is approached arbitrarily closely from Y<0; nearby explicit Y<0 witness also checked below.',
 'method':'Clip original nasal triangles by channel-wall YZ halfspaces, find lateral extreme of clipped polygons, project to channel-wall X=+/-13. This is an exact continuous triangle-to-wall witness. Final full case triangles still required for global minimum.',
 'meets_2mm':best[0]>=2}
# Explicit witness on same triangle with Y<0 avoids a boundary-only argument.
face=tri[best[2]]
negative=face[face[:,1]<0]
if len(negative):
    eps=1e-5
    p=best[1]*(1-eps)+negative[negative[:,1].argmin()]*eps
    w=p.copy();w[0]=13*np.sign(w[0])
    report['explicit_negative_y_witness']={'nose_xyz_mm':p.tolist(),'case_xyz_mm':w.tolist(),'distance_mm':float(np.linalg.norm(p-w))}
(P/'channel_case_nose_witness.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
