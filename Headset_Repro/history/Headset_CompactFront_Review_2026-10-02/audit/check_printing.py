from pathlib import Path
import json,math
import numpy as np
P=Path(__file__).resolve().parent;ROOT=P.parents[1];G=P.parent/'geometry'
a=math.radians(-65);c,s=math.cos(a),math.sin(a);R=np.array([[1,0,0],[0,c,-s],[0,s,c]])
bup=R[2];report={'rotation_x_deg':-65,'printing_coordinates_not_applied_to_delivered_model':True,'wing_internal_45_degree_geometry_only':{}}
for name in ['left','right']:
 p=ROOT/'Headset_CompactFront_Review_2026-10-02/inputs'/('air_sealed_'+name+'.npz');m=np.load(p);v,f=m['v'],m['f'];tri=v[f];n=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);n/=np.linalg.norm(n,axis=1,keepdims=True)
 co=n@bup;idx=int(co.argmax());report['wing_internal_45_degree_geometry_only'][name]={'method':'Retained wing void faces from prior genuine sealed void; the0.03mm camera-boundary crop adds no less favorable ceiling orientation. Current global solid has0 fully sealed voids, but these narrow wing spaces are conservatively treated as inaccessible to support removal.','maximum_ceiling_cos':float(co[idx]),'minimum_ceiling_angle_deg':float(math.degrees(math.acos(np.clip(co[idx],-1,1)))),'below45_face_count':int((co>math.sqrt(.5)+1e-8).sum())}
m=np.load(G/'front_unified_preview.npz');v=m['v']@R.T;report['print_bbox_mm']=(v.max(0)-v.min(0)).tolist()
gv=json.loads((G/'geometry_values.json').read_text());N=np.array([0,*gv['chamfer_inner_outward_normal_yz']]);report['accessible_chamfer_ceiling_angle_deg']=float(math.degrees(math.acos(float(N@bup))))
report['supports_required']='Accessible inner front-upper chamfer; original face-side overhangs, arm/tab ends. No supports placed in narrow wing spaces. Slicer, removal and actual hook flexibility not tested.'
(P/'printing_geometry.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report,indent=2))
