"""Check ordinary small head pitch changes; never scale the head."""
from pathlib import Path
import runpy, json
import numpy as np
P=Path(__file__).resolve().parent
d=runpy.run_path(str(P/'register_head.py'))
H,HF,EARS,NOTCH=d['H'],d['HF'],d['EARS'],d['NOTCH']
tn=H[HF]
rows=[]
for pitch in [-10,-5,0,5,10]:
    a=np.deg2rad(pitch)
    R=np.array([[1,0,0],[0,-np.sin(a),-np.cos(a)],[0,np.cos(a),-np.sin(a)]])
    ear=EARS@R.T; dz=d['arm_min_z']-ear[:,2].mean()
    xy=np.stack([tn[:,:,0],tn@R[2]],axis=-1)
    p0,p1,p2=xy[:,0],xy[:,1],xy[:,2];target=np.array([0.,NOTCH[2]-dz])
    def cross2(u,v):return u[:,0]*v[:,1]-u[:,1]*v[:,0]
    det=cross2(p1-p0,p2-p0)
    bb=np.divide(cross2(target-p0,p2-p0),det,out=np.zeros(len(det)),where=np.abs(det)>1e-16)
    cc=np.divide(cross2(p1-p0,target-p0),det,out=np.zeros(len(det)),where=np.abs(det)>1e-16)
    inside=(np.abs(det)>1e-16)&(bb>=0)&(cc>=0)&(bb+cc<=1)
    hit=tn[:,0]*(1-bb-cc)[:,None]+tn[:,1]*bb[:,None]+tn[:,2]*cc[:,None]
    hit=hit[inside];bridge=hit[(hit@R[1]).argmin()]
    shift=np.array([0.,NOTCH[1]-(bridge@R[1]),dz]);V=H@R.T+shift
    tri=V[HF];ok=(np.abs(tri[:,:,0]).max(1)<20)&(tri[:,:,2].max(1)>0)&(tri[:,:,2].min(1)<37)&(tri[:,:,1].min(1)<20)
    # The exact function's module globals are the runpy dictionary.
    fun=d['exact_tri_distance'];fun.__globals__['nasal_tri']=tri[ok]
    nominal=fun();allowed=fun(.563888)
    lo,hi=0,10
    for _ in range(50):
        mid=(lo+hi)/2
        if fun(mid)[0]<3:lo=mid
        else:hi=mid
    core=d['section'](V,HF,2,45.)
    core=core[(core[:,1]>80)&(core[:,1]<147)]
    reached=fun(hi)[0]>=3-1e-9
    rows.append({'pitch_deg':pitch,'head_scale':1,'nominal_gap_mm':nominal[0],'allowed_lift_gap_mm':allowed[0],'lift_for_3mm_mm':hi if reached else None,'search_status':'3mm reached within search range' if reached else 'not reached by10mm raise; monotonicity not established','head_breadth_at_world_z45_between_y80_147_mm':float(np.ptp(core[:,0])) if len(core) else None,'nose_point_world_mm':nominal[1].tolist(),'matrix_rotation':R.tolist(),'translation_xyz_mm':shift.tolist()})
(P/'pitch_sensitivity.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
print(json.dumps(rows,indent=2))
