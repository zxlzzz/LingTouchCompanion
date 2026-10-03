"""Continuous triangle distance with independent closest-feature witnesses.

Open surfaces are allowed. NumPy handles triangle pairs; the global solver
uses SciPy's cKDTree only for conservative broadphase pruning. No project
history, fitted ellipsoid, convex proxy or vertex-only answer is consumed.
"""
import numpy as np


def closest_points(P,A,B,C):
    """Closest points on ABC for broadcast arrays of query points P."""
    P,A,B,C=np.broadcast_arrays(P,A,B,C)
    ab,ac,ap=B-A,C-A,P-A
    d1=(ab*ap).sum(-1);d2=(ac*ap).sum(-1)
    bp=P-B;d3=(ab*bp).sum(-1);d4=(ac*bp).sum(-1)
    cp=P-C;d5=(ab*cp).sum(-1);d6=(ac*cp).sum(-1)
    vc=d1*d4-d3*d2;vb=d5*d2-d1*d6;va=d3*d6-d5*d4
    den=va+vb+vc
    v=np.divide(vb,den,out=np.zeros_like(den),where=np.abs(den)>1e-30)
    w=np.divide(vc,den,out=np.zeros_like(den),where=np.abs(den)>1e-30)
    Q=A+v[...,None]*ab+w[...,None]*ac
    mask=(d1<=0)&(d2<=0);Q[mask]=A[mask]
    mask=(d3>=0)&(d4<=d3);Q[mask]=B[mask]
    mask=(d6>=0)&(d5<=d6);Q[mask]=C[mask]
    mask=(vc<=0)&(d1>=0)&(d3<=0)
    frac=np.divide(d1,d1-d3,out=np.zeros_like(d1),where=np.abs(d1-d3)>1e-30)
    Q[mask]=(A+frac[...,None]*ab)[mask]
    mask=(vb<=0)&(d2>=0)&(d6<=0)
    frac=np.divide(d2,d2-d6,out=np.zeros_like(d2),where=np.abs(d2-d6)>1e-30)
    Q[mask]=(A+frac[...,None]*ac)[mask]
    mask=(va<=0)&((d4-d3)>=0)&((d5-d6)>=0)
    frac=np.divide(d4-d3,(d4-d3)+(d5-d6),out=np.zeros_like(d1),where=np.abs((d4-d3)+(d5-d6))>1e-30)
    Q[mask]=(B+frac[...,None]*(C-B))[mask]
    return Q


def pair_distance(H,C):
    """Exact minimum for corresponding triangle pairs, with both witnesses."""
    H=np.asarray(H,dtype=float);C=np.asarray(C,dtype=float)
    best=np.full(len(H),np.inf);pb=np.zeros((len(H),3));qb=pb.copy()
    def offer(p,q,valid=None):
        ds=((p-q)**2).sum(1)
        if valid is not None:ds[~valid]=np.inf
        keep=ds<best;best[keep]=ds[keep];pb[keep]=p[keep];qb[keep]=q[keep]
    for j in range(3):
        p=H[:,j];q=closest_points(p,C[:,0],C[:,1],C[:,2]);offer(p,q)
        q=C[:,j];p=closest_points(q,H[:,0],H[:,1],H[:,2]);offer(p,q)
    # Interior edge/face crossing can give zero without a vertex/face or
    # edge/edge minimum attaining zero. Test all six finite edge/face cases.
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


def continuous_min(V,F,CV,CF,progress=False):
    """Continuous global triangle minimum; never seed with unreferenced points."""
    from scipy.spatial import cKDTree
    V=np.asarray(V,dtype=float);CV=np.asarray(CV,dtype=float)
    F=np.asarray(F,dtype=np.int64);CF=np.asarray(CF,dtype=np.int64)
    if not len(F) or not len(CF):raise ValueError('Both meshes need triangle faces')
    H=V[F];C=CV[CF];HC=H.mean(1);HR=np.linalg.norm(H-HC[:,None],axis=2).max(1)
    tree=cKDTree(HC);hm=float(HR.max())
    refs=np.unique(F.ravel());crefs=np.unique(CF.ravel())
    d,ix=cKDTree(V[refs]).query(CV[crefs]);ci=int(d.argmin())
    best=[float(d[ci]),V[refs[int(ix[ci])]],CV[crefs[ci]],-1,-1]
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
        if progress and start%6400==0:print('continuous',start,'of',len(C),'best',best[0],flush=True)
    return {'distance_mm':best[0],'head_witness_xyz_mm':best[1].tolist(),'case_witness_xyz_mm':best[2].tolist(),'head_face_index':best[3],'case_face_index':best[4],'broadphase_pairs':candidates,'exact_pairs_tested':tested,'method':'Conservative enclosing-sphere and AABB broadphase; every vertex-face and interior edge-edge minimum plus all six edge-face intersection tests per possibly closer triangle pair. Exterior/penetration classification is checked separately.'}
