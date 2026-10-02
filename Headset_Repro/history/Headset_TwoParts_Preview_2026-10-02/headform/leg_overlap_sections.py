from pathlib import Path
import json,numpy as np
P=Path(__file__).resolve().parent;R=P.parents[1]
h=np.load(P/'Medium_Trial_Registered.npz');H,HF=h['v'],h['f']
g=np.load(R/'Headset_Prop_Stage1_2026-10-02/reference_normal_mesh.npz');G=g['vertices']+[0,73.53516495,27.587837475];GF=g['faces']
def xhits(v,f,y,z):
    tri=v[f];q=tri[:,:,[1,2]];a,b,c=q[:,0],q[:,1],q[:,2];target=np.array([y,z])
    def cr(u,v):return u[:,0]*v[:,1]-u[:,1]*v[:,0]
    det=cr(b-a,c-a)
    bb=np.divide(cr(target-a,c-a),det,out=np.zeros(len(det)),where=np.abs(det)>1e-16)
    cc=np.divide(cr(b-a,target-a),det,out=np.zeros(len(det)),where=np.abs(det)>1e-16)
    inside=(np.abs(det)>1e-16)&(bb>=0)&(cc>=0)&(bb+cc<=1)
    xx=tri[:,0,0]*(1-bb-cc)+tri[:,1,0]*bb+tri[:,2,0]*cc
    return np.unique(np.round(xx[inside],8))
rows=[]
for y in [95.,100.,110.,120.,125.,135.]:
    for z in [37.5,45.,51.]:
        hh=xhits(H,HF,y,z);gg=xhits(G,GF,y,z)
        if len(hh) and len(gg):
            right=gg[gg>0];left=gg[gg<0]
            rows.append({'y_mm':y,'z_mm':z,'head_x_intersections_mm':hh.tolist(),'frame_x_intersections_mm':gg.tolist(),'right_outer_leg_inset_under_head_surface_mm':float(hh.max()-right.max()) if len(right) else None,'left_outer_leg_inset_under_head_surface_mm':float(left.min()-hh.min()) if len(left) else None})
(P/'leg_overlap_sections.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
print(json.dumps(rows,indent=2))
