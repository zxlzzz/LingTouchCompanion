"""Read-only measurements of original BTTF Normal surfaces."""
from pathlib import Path
import json,math
import numpy as np
P=Path(__file__).resolve().parent
SOURCE=P.parents[1]/'Headset_FullCase_30mm_Preview_2026-10-02/preview_work/original_reference.npz'
A=np.load(SOURCE);v=A['v'];f=A['f'];tri=v[f]
a,b,c=tri[:,0],tri[:,1],tri[:,2]
den=(b[:,2]-c[:,2])*(a[:,0]-c[:,0])+(c[:,0]-b[:,0])*(a[:,2]-c[:,2])
valid=np.abs(den)>1e-12
xmin=tri[:,:,0].min(1);xmax=tri[:,:,0].max(1);zmin=tri[:,:,2].min(1);zmax=tri[:,:,2].max(1)
def ray(x,z):
 ids=np.where(valid&(xmin<=x+1e-9)&(xmax>=x-1e-9)&(zmin<=z+1e-9)&(zmax>=z-1e-9))[0]
 aa,bb,cc=a[ids],b[ids],c[ids];dd=den[ids]
 p=((bb[:,2]-cc[:,2])*(x-cc[:,0])+(cc[:,0]-bb[:,0])*(z-cc[:,2]))/dd
 q=((cc[:,2]-aa[:,2])*(x-cc[:,0])+(aa[:,0]-cc[:,0])*(z-cc[:,2]))/dd
 hit=(p>=-1e-7)&(q>=-1e-7)&(p+q<=1+1e-7)
 yy=p[hit]*aa[hit,1]+q[hit]*bb[hit,1]+(1-p[hit]-q[hit])*cc[hit,1]
 return np.unique(np.round(yy,10)).tolist()
C=math.cos(math.radians(20));S=math.sin(math.radians(20));tan=S/C
report={'source':str(SOURCE),'original_bounds':[v.min(0).tolist(),v.max(0).tolist()],'top_formula_Z_for_h32p3':'58.264118238384924+0.36397023426620234*Y','Y_at_Z60':(60-23.6-32.3/C)/tan-.8,'rows':[]}
for x in [-65,-47.27,-45.3,-30,-15,0,15,30,45.3,47.27,65]:
 for z in [2,15,25,35,45,55.17567495-1e-5]:
  ys=ray(x,z);front=[y for y in ys if y<60]
  report['rows'].append({'x':x,'z':z,'front_surface_hits_y':front,'top_at_max_face_y':None if not front else 23.6+32.3/C+tan*(max(front)+.8)})
(P/'original_surface_probe.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report,indent=2))
