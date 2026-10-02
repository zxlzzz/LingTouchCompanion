"""Rigid Medium headform trial seating; no scale or frame alterations."""
from pathlib import Path
import numpy as np, json
from scipy.spatial import cKDTree

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
g=np.load(ROOT/'Headset_Prop_Stage1_2026-10-02/reference_normal_mesh.npz')
G=g['vertices'].copy()+[0,73.53516495,27.587837475];GF=g['faces']
h=np.load(ROOT/'Headset_Layout_v15/reference/Medium_Symmetry.npz')
H=h['v'];HF=h['f']
def section(mesh,faces,axis,value):
    tri=mesh[faces];hits=[]
    for a,b in [(0,1),(1,2),(2,0)]:
        pa,pb=tri[:,a],tri[:,b]
        active=((pa[:,axis]<=value)&(pb[:,axis]>value))|((pb[:,axis]<=value)&(pa[:,axis]>value))
        aa,bb=pa[active],pb[active]
        q=aa+(bb-aa)*((value-aa[:,axis])/(bb[:,axis]-aa[:,axis]))[:,None]
        hits.append(q)
    return np.vstack(hits)
GS=section(G,GF,0,0)
rim=GS[(GS[:,1]<4)&(GS[:,2]<30)&(GS[:,2]>10)]
NOTCH=rim[rim[:,2].argmin()]
# Upper anterior ear-root points visually selected on the original anatomical
# mesh, rather than outermost helix. Nearest original vertices to the stated
# region targets make this manual selection reproducible. NIOSH does not tag
# ear-root landmarks in the distributed STL.
EARS=[]
for sign in [-1,1]:
    ear=H[(sign*H[:,0]>70)&(sign*H[:,0]<79)&(H[:,1]>10)&(H[:,1]<27)&(H[:,2]>-15)&(H[:,2]<4)]
    target=np.array([sign*75.5,20,-5.])
    EARS.append(ear[np.linalg.norm(ear-target,axis=1).argmin()])
EARS=np.array(EARS)
arm_min_z=float(G[G[:,1]>115,2].min())
dz=arm_min_z-EARS[:,1].mean()
bridge_height=NOTCH[2]-dz
tri_native=H[HF]
a,b,c=tri_native[:,0,:2],tri_native[:,1,:2],tri_native[:,2,:2]
def cross2(u,v):return u[:,0]*v[:,1]-u[:,1]*v[:,0]
det=cross2(b-a,c-a);target=np.array([0.,bridge_height])
bb=np.divide(cross2(target-a,c-a),det,out=np.zeros(len(det)),where=np.abs(det)>1e-16)
cc=np.divide(cross2(b-a,target-a),det,out=np.zeros(len(det)),where=np.abs(det)>1e-16)
inside=(np.abs(det)>1e-16)&(bb>=0)&(cc>=0)&(bb+cc<=1)
line_hits=tri_native[:,0]*(1-bb-cc)[:,None]+tri_native[:,1]*bb[:,None]+tri_native[:,2]*cc[:,None]
line_hits=line_hits[inside]
bridge=line_hits[line_hits[:,2].argmax()]
# Rigid anatomical orientation: native superior Y -> +Z, anterior Z -> -Y.
R=np.array([[1,0,0],[0,0,-1],[0,1,0.]])
shift=np.array([-bridge[0],NOTCH[1]+bridge[2],dz])
T=np.eye(4);T[:3,:3]=R;T[:3,3]=shift
V=H@R.T+shift
np.savez_compressed(HERE/'Medium_Trial_Registered.npz',v=V,f=HF)
np.savez_compressed(HERE/'medium_native.npz',v=H,f=HF)
ears_world=EARS@R.T+shift
# Measure actual head surface points and triangle samples in nasal region.
tri=V[HF]
nasal_faces=(np.abs(tri[:,:,0]).max(1)<20)&(tri[:,:,2].max(1)>0)&(tri[:,:,2].min(1)<37)&(tri[:,:,1].min(1)<20)
nasal_tri=tri[nasal_faces]
points=[nasal_tri.reshape(-1,3)]
for den in [2,4]:
    for a in range(den+1):
        for b in range(den-a+1):
            points.append((nasal_tri[:,0]*a+nasal_tri[:,1]*b+nasal_tri[:,2]*(den-a-b))/den)
P=np.vstack(points)
angle=np.deg2rad(20)
UP=np.array([0,-np.sin(angle),np.cos(angle)])
FW=np.array([0,-np.cos(angle),-np.sin(angle)])
origin=np.array([0,-.8,23.6])
def to_rectangle(points,lift=0):
    delta=points-origin-[0,0,lift]
    x=delta[:,0];t=delta@FW;q=delta@UP
    close=origin+[0,0,lift]+np.column_stack([np.clip(x,-47.27,47.27),np.zeros(len(x)),np.zeros(len(x))])+np.clip(t,-2,15)[:,None]*FW-2.5*UP
    d=np.linalg.norm(points-close,axis=1)
    k=d.argmin()
    return float(d[k]),points[k],close[k],float(q[k]+2.5)
def exact_tri_distance(lift=0):
    """Exact closest-feature distance after valid orthogonal X elimination.

    All selected nose triangles have X within the rectangle's full width.
    The rectangle spans X continuously, so min X difference is zero; the
    3-D minimum reduces exactly to triangle projections in (t,q) vs segment.
    """
    delta=nasal_tri-origin-[0,0,lift]
    Q=np.stack([delta@FW,delta@UP],axis=-1)
    endpoints=np.array([[-2.,-2.5],[15.,-2.5]])
    dist_best=float('inf'); nose_best=None; rect_best=None
    for k in range(3):
        q=Q[:,k]; nearest=np.column_stack([np.clip(q[:,0],-2,15),np.full(len(q),-2.5)])
        ds=np.linalg.norm(q-nearest,axis=1);i=ds.argmin()
        if ds[i]<dist_best:
            dist_best=float(ds[i]);nose_best=nasal_tri[i,k];
            rect_best=origin+[0,0,lift]+[nose_best[0],0,0]+nearest[i,0]*FW+nearest[i,1]*UP
    for a,b in [(0,1),(1,2),(2,0)]:
        pa,pb=Q[:,a],Q[:,b];ab=pb-pa;length2=(ab*ab).sum(1)
        for endpoint in endpoints:
            frac=np.divide(((endpoint-pa)*ab).sum(1),length2,out=np.zeros(len(ab)),where=length2>1e-16)
            frac=np.clip(frac,0,1);close=pa+frac[:,None]*ab
            ds=np.linalg.norm(endpoint-close,axis=1);i=ds.argmin()
            if ds[i]<dist_best:
                dist_best=float(ds[i]);nose_best=nasal_tri[i,a]+frac[i]*(nasal_tri[i,b]-nasal_tri[i,a]);
                rect_best=origin+[0,0,lift]+[nose_best[0],0,0]+endpoint[0]*FW+endpoint[1]*UP
        cross=(pa[:,1]+2.5)*(pb[:,1]+2.5)<=0
        frac=np.divide(-2.5-pa[:,1],ab[:,1],out=np.zeros(len(ab)),where=np.abs(ab[:,1])>1e-16)
        tcross=pa[:,0]+frac*ab[:,0]
        cross &= (frac>=0)&(frac<=1)&(tcross>=-2)&(tcross<=15)
        if cross.any():
            i=np.flatnonzero(cross)[0];point=nasal_tri[i,a]+frac[i]*(nasal_tri[i,b]-nasal_tri[i,a]);return 0.,point,point
    # Segment endpoints inside projected triangles also imply zero distance.
    a,b,c=Q[:,0],Q[:,1],Q[:,2]
    def cross2(u,v):return u[:,0]*v[:,1]-u[:,1]*v[:,0]
    det=cross2(b-a,c-a)
    for endpoint in endpoints:
        bb=np.divide(cross2(endpoint-a,c-a),det,out=np.zeros(len(det)),where=np.abs(det)>1e-16)
        cc=np.divide(cross2(b-a,endpoint-a),det,out=np.zeros(len(det)),where=np.abs(det)>1e-16)
        inside=(np.abs(det)>1e-16)&(bb>=0)&(cc>=0)&(bb+cc<=1)
        if inside.any():
            i=np.flatnonzero(inside)[0];point=nasal_tri[i,0]*(1-bb[i]-cc[i])+nasal_tri[i,1]*bb[i]+nasal_tri[i,2]*cc[i];return 0.,point,point
    return dist_best,nose_best,rect_best
best=exact_tri_distance()
lo,hi=0.,10.
for _ in range(50):
    mid=(lo+hi)/2
    if exact_tri_distance(mid)[0]<3:lo=mid
    else:hi=mid
lift=hi;raised=exact_tri_distance(lift)
allowed_lift=.563888
allowed=exact_tri_distance(allowed_lift)
SG=section(V,HF,0,0)
nose_curve=SG[(SG[:,1]<30)&(SG[:,2]>0)&(SG[:,2]<45)]
nose_curve=nose_curve[np.argsort(nose_curve[:,2])]
np.savez_compressed(HERE/'nose_center_section.npz',xyz=nose_curve)
# Actual surface vs fixed arm region: arms occupy x~=67.4..71.0 and z34.33..55.18.
# Cross-sections report head lateral surface at the same arm height and Y.
cuts=[]
for z in [35.,37.5,45.,51.]:
    S=section(V,HF,2,z)
    # Neck/back sections excluded; span is the original straight leg reach.
    S=S[(S[:,1]>80)&(S[:,1]<147)]
    if len(S):cuts.append({'z_mm':z,'head_x_range_mm':[float(S[:,0].min()),float(S[:,0].max())],'head_breadth_mm':float(np.ptp(S[:,0])),'max_over_135_mm':float(np.ptp(S[:,0])-135)})
# Check head vertices residing in broad original arm AABBs; this is not a triangle
# collision proof, so name it candidly and retain parent exact collision task.
arm_region=V[(np.abs(V[:,0])>67.4)&(np.abs(V[:,0])<71.16)&(V[:,1]>80)&(V[:,1]<147.071)&(V[:,2]>34.33)&(V[:,2]<55.176)]
report={
 'headform':'NIOSH ISO Medium Symmetry, RD-10130-2020-0','scale':1,'native_units':'mm',
 'source_url':'https://archive.cdc.gov/www_cdc_gov/niosh/npptl/topics/respirators/headforms/default.html',
 'native_to_current_matrix':T.tolist(),
 'seating_status':'Trial contact registration only. Full original-frame fit is not established; fixed135mm arms interfere with unscaled headform.',
 'registration_method':'Trial only: keep anatomical axes level. Original notch sagittal apex contacts anterior nose bridge. Mean upper anterior inner ear-root height is matched to original rear-leg minimum Z. Ear-root vertices are nearest original vertices to manually selected targets (native X +/-75.5, Y20, Z-5), constrained70<abs(X)<79,10<Y<27,-15<Z<4. Nose and ear vertical positions match, but rigid legs are laterally inside the head and therefore cannot contact these roots. No scale or deformation.',
 'notch_apex_current_xyz_mm':NOTCH.tolist(),'nose_bridge_native_xyz_mm':bridge.tolist(),'nose_bridge_current_xyz_mm':(bridge@R.T+shift).tolist(),
 'ear_native_xyz_mm':EARS.tolist(),'ear_current_xyz_mm':ears_world.tolist(),'ear_contact_target_leg_bottom_z_mm':arm_min_z,
 'socket_underside_definition':{'origin_xyz_mm':origin.tolist(),'q_mm':-2.5,'x_mm':[-47.27,47.27],'t_mm':[-2,15],'up_vector':UP.tolist(),'forward_vector':FW.tolist()},
 'nominal_nearest_nose_to_underside_mm':best[0],'nominal_nose_point_mm':best[1].tolist(),'nominal_socket_point_mm':best[2].tolist(),
 'raise_for_3mm_clearance_mm':lift,'raised_nearest_clearance_mm':raised[0],'raised_nose_point_mm':raised[1].tolist(),'raised_socket_point_mm':raised[2].tolist(),
 'allowed_raise_mm':allowed_lift,'allowed_raise_nearest_clearance_mm':allowed[0],'allowed_raise_nose_point_mm':allowed[1].tolist(),'allowed_raise_socket_point_mm':allowed[2].tolist(),
 'distance_method':'Continuous minimum between original nasal triangles and the analytic bottom rectangle. Selected nasal triangles have X entirely within rectangle width, so eliminate X orthogonally, project triangles onto (t,q), and evaluate segment-triangle intersection, vertex-to-segment, segment endpoint-to-triangle-edge and endpoint-in-triangle cases. Unsigned separation; full original-frame fit assessed separately.',
 'head_cross_section_between_y80_147_mm':cuts,'vertices_in_broad_original_leg_aabbs':len(arm_region),
 'limits':'No unscaled NIOSH headform is explicitly labeled56cm. Head circumference proxy for Medium nativeY35 is551.963mm and core width150.834mm; this is not wearer-specific fit proof. Ear-root points are manually identified and reproducibly selected existing mesh vertices, not tagged supplier landmarks. This is a YZ trial seating because rigid arms prevent actual three-dimensional wearing.'}
(HERE/'head_registration_new.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
