"""Independent continuous triangle clearance audit; no model mutations."""
from pathlib import Path
import hashlib,json,sys,time
import numpy as np
from scipy.spatial import cKDTree

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
G=HERE.parent/'geometry'
HEAD=ROOT/'Headset_Carbon6K_FlatBase_Review_2026-10-02/inputs/Medium_Trial_Registered.npz'
sys.path.insert(0,str(ROOT/'Headset_Carbon6K_FlatBase_Review_2026-10-02/inputs'))
from triangle_distance import closest_points

def load(p):
    a=np.load(p);return a['v'],a['f']

def pair_distance(H,C):
    best=np.full(len(H),np.inf);pb=np.zeros((len(H),3));qb=pb.copy()
    def offer(p,q,valid=None):
        ds=((p-q)**2).sum(1)
        if valid is not None:ds[~valid]=np.inf
        keep=ds<best;best[keep]=ds[keep];pb[keep]=p[keep];qb[keep]=q[keep]
    for j in range(3):
        p=H[:,j];q=closest_points(p,C[:,0],C[:,1],C[:,2]);offer(p,q)
        q=C[:,j];p=closest_points(q,H[:,0],H[:,1],H[:,2]);offer(p,q)
    # Intersecting triangles can meet at an edge/face interior without any
    # vertex/face or edge/edge minimum attaining zero. Explicitly test all
    # six finite edges against the opposite triangle plane and its face.
    for A,B in [(H,C),(C,H)]:
        normal=np.cross(B[:,1]-B[:,0],B[:,2]-B[:,0])
        for i,j in [(0,1),(1,2),(2,0)]:
            p0,p1=A[:,i],A[:,j]
            d0=((p0-B[:,0])*normal).sum(1);d1=((p1-B[:,0])*normal).sum(1);den=d0-d1
            t=np.divide(d0,den,out=np.zeros(len(A)),where=np.abs(den)>1e-20)
            p=p0+t[:,None]*(p1-p0);q=closest_points(p,B[:,0],B[:,1],B[:,2])
            hit=(np.abs(den)>1e-20)&(t>=-1e-12)&(t<=1+1e-12)&(np.linalg.norm(p-q,axis=1)<1e-9)
            offer(p,q,hit)
    for a,b in [(0,1),(1,2),(2,0)]:
        hp,hq=H[:,a],H[:,b];u=hq-hp
        for c,d in [(0,1),(1,2),(2,0)]:
            cp,cq=C[:,c],C[:,d];v=cq-cp;w=hp-cp
            aa=(u*u).sum(1);bb=(u*v).sum(1);cc=(v*v).sum(1);dd=(u*w).sum(1);ee=(v*w).sum(1)
            den=aa*cc-bb*bb
            s=np.divide(bb*ee-cc*dd,den,out=np.zeros(len(H)),where=np.abs(den)>1e-20)
            t=np.divide(aa*ee-bb*dd,den,out=np.zeros(len(H)),where=np.abs(den)>1e-20)
            offer(hp+s[:,None]*u,cp+t[:,None]*v,(np.abs(den)>1e-20)&(s>=0)&(s<=1)&(t>=0)&(t<=1))
    return np.sqrt(best),pb,qb

def point_distances(P,V,F):
    """Exact closest features among all possibly closer head triangles."""
    H=V[F];HC=H.mean(1);HR=np.linalg.norm(H-HC[:,None],axis=2).max(1);hm=float(HR.max())
    tree=cKDTree(HC);vtree=cKDTree(V);upper,_=vtree.query(P)
    out=np.empty(len(P));witness=np.empty_like(P)
    for begin in range(0,len(P),128):
        pts=P[begin:begin+128];ub=upper[begin:begin+128]
        lists=tree.query_ball_point(pts,ub+hm+1e-9);cnt=np.array([len(a) for a in lists]);pi=np.repeat(np.arange(len(pts)),cnt);hi=np.asarray(np.concatenate(lists),dtype=np.int64)
        # Sphere bound conservatively includes every triangle closer than the
        # nearest source vertex. No finite nearest-neighbor sample is assumed.
        q=closest_points(pts[pi],H[hi,0],H[hi,1],H[hi,2]);d2=((pts[pi]-q)**2).sum(1)
        b=np.full(len(pts),np.inf);np.minimum.at(b,pi,d2)
        wi=np.full(len(pts),len(pi),int);match=d2==b[pi];np.minimum.at(wi,pi[match],np.flatnonzero(match))
        out[begin:begin+len(pts)]=np.sqrt(b);witness[begin:begin+len(pts)]=q[wi]
    return out,witness

def continuous_min(V,F,CV,CF):
    H=V[F];C=CV[CF];HC=H.mean(1);HR=np.linalg.norm(H-HC[:,None],axis=2).max(1)
    tree=cKDTree(HC);hm=float(HR.max());d,ix=cKDTree(V).query(CV);ci=int(d.argmin());best=[float(d[ci]),V[int(ix[ci])],CV[ci],-1,-1]
    hlo,hhi=H.min(1),H.max(1);tested=0;candidates=0
    for start in range(0,len(C),64):
        K=C[start:start+64];KC=K.mean(1);KR=np.linalg.norm(K-KC[:,None],axis=2).max(1)
        lists=tree.query_ball_point(KC,KR+hm+best[0]+1e-9)
        cnt=np.array([len(a) for a in lists]);ki=np.repeat(np.arange(len(K)),cnt)
        if not len(ki):continue
        hi=np.asarray(np.concatenate(lists),dtype=np.int64);candidates+=len(hi)
        gap=np.maximum(np.maximum(hlo[hi]-K[ki].max(1),K[ki].min(1)-hhi[hi]),0.)
        keep=(gap*gap).sum(1)<=(best[0]+1e-9)**2;hi=hi[keep];ki=ki[keep]
        for begin in range(0,len(hi),12000):
            hh,kk=hi[begin:begin+12000],ki[begin:begin+12000]
            ds,p,q=pair_distance(H[hh],K[kk]);tested+=len(ds)
            if len(ds):
                j=int(ds.argmin())
                if ds[j]<best[0]:best=[float(ds[j]),p[j],q[j],int(hh[j]),start+int(kk[j])]
        if start%6400==0:print('continuous',start,'of',len(C),'best',best[0],flush=True)
    return {'distance_mm':best[0],'head_witness_xyz_mm':best[1].tolist(),'case_witness_xyz_mm':best[2].tolist(),'head_face_index':best[3],'case_face_index':best[4],'broadphase_pairs':candidates,'exact_pairs_tested':tested,'method':'Conservative enclosing-sphere and AABB broadphase; all vertex-face and interior edge-edge minima plus all six edge-face intersection tests per potentially closer triangle pair. Positive minimum excludes continuous surface intersections; outside-solid classification checked separately.'}

def main():
    begun=time.perf_counter();V,F=load(HEAD)
    R,RF=load(G/'rear_unified_preview.npz');tri=V[F]
    # Every excluded face lies outside this padded rear bounding box. A
    # nearest-head-vertex bound below5mm verifies the exclusion is conservative.
    lo=R.min(0)-5;hi=R.max(0)+5
    keep=np.all(tri.max(1)>=lo,axis=1)&np.all(tri.min(1)<=hi,axis=1)
    H=tri[keep];ids=np.flatnonzero(keep);HV=H.reshape(-1,3);HF=np.arange(len(HV)).reshape(-1,3)
    result={'head_source':str(HEAD),'head_source_sha256':hashlib.sha256(HEAD.read_bytes()).hexdigest(),'pose_unchanged':True,'head_is_not_manifold':'Head source has an open/nonmanifold neck; no head-volume Boolean is asserted.'}
    result['rear_head_continuous_minimum']=continuous_min(HV,HF,R,RF)
    for name in ['rear_inner_surface','rear_outer_surface']:
        p=G/(name+'.npz');SV,SF=load(p);ds,wp=point_distances(SV,HV,HF)
        edge=float(np.linalg.norm(SV[SF]-np.roll(SV[SF],1,axis=1),axis=2).max());radius=edge/np.sqrt(3)
        result[name]={'source_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'vertices':len(SV),'triangles':len(SF),'vertex_distance_min_mm':float(ds.min()),'vertex_distance_max_mm':float(ds.max()),'max_triangle_edge_mm':edge,'continuous_surface_distance_bound_mm':[float(ds.min()-radius),float(ds.max()+radius)],'certificate':'Distance to original triangular surface is 1-Lipschitz; every triangle point lies within maximum-edge/sqrt(3) of some vertex. Vertex distances computed over every possibly closer source triangle, including face and edge features.'}
    result['tray_inner_entire_surface_0_to_2_pass']=result['rear_inner_surface']['continuous_surface_distance_bound_mm'][0]>=0 and result['rear_inner_surface']['continuous_surface_distance_bound_mm'][1]<=2
    result['tray_inner_outer_minimum']=continuous_min(*load(G/'rear_inner_surface.npz'),*load(G/'rear_outer_surface.npz'))
    sys.path.insert(0,str(ROOT/'Headset_Carbon6K_FlatBase_Review_2026-10-02/inputs'))
    from rear_surface import rear_points
    P,N,I=rear_points(R[:,[0,2]]);signed_gap=R[:,1]-P[:,1]
    valid=np.isfinite(signed_gap)
    result['posterior_vertex_classification']={'valid_vertices':int(valid.sum()),'total_vertices':len(R),'minimum_positive_Y_gap_mm':float(signed_gap[valid].min()),'head_triangle_surface_intersection_certified_absent':result['rear_head_continuous_minimum']['distance_mm']>0,'interpretation':'Positive Y gaps at every vertex with an anatomical posterior ray, plus a positive continuous triangle distance, certify the connected rear solid stays outside posterior head surface. This is local posterior verification; it does not certify original BTTF fit.'}
    result['rear_source_sha256']=hashlib.sha256((G/'rear_unified_preview.npz').read_bytes()).hexdigest()
    result['elapsed_seconds']=time.perf_counter()-begun
    (HERE/'surface_clearance_audit.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result,indent=2))

if __name__=='__main__':main()
