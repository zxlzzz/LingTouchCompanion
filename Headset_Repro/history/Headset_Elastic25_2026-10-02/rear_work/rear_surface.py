"""Original-triangle posterior head surface queried by exact +Y ray hits."""
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
HEAD_SOURCE=ROOT/'Headset_FullCase_30mm_Preview_2026-10-02/headform/Medium_Trial_Registered.npz'
DATA=np.load(HEAD_SOURCE);V,F=DATA['v'],DATA['f'];TRI=V[F]
raw_normal=np.cross(TRI[:,1]-TRI[:,0],TRI[:,2]-TRI[:,0])
normal=raw_normal/np.maximum(np.linalg.norm(raw_normal,axis=1)[:,None],1e-15)
vertex_normal=np.zeros_like(V)
for j in range(3):np.add.at(vertex_normal,F[:,j],raw_normal)
vertex_normal/=np.maximum(np.linalg.norm(vertex_normal,axis=1)[:,None],1e-15)
posterior=(TRI[:,:,1].max(1)>110)&(TRI[:,:,2].max(1)>=-3.5)&(TRI[:,:,2].min(1)<=58.7)
IDS=np.flatnonzero(posterior);T=TRI[IDS];N=normal[IDS]
A,B,C=T[:,0][:,[0,2]],T[:,1][:,[0,2]],T[:,2][:,[0,2]]
TREE=cKDTree(T[:,:,[0,2]].mean(1))
OFFSET_CELL=2.
OFFSET_BUCKETS={}
for i,(lo,hi) in enumerate(zip(T[:,:,[0,2]].min(1)-3.5,T[:,:,[0,2]].max(1)+3.5)):
    ilo,ihi=np.floor(lo/OFFSET_CELL).astype(int),np.floor(hi/OFFSET_CELL).astype(int)
    for cx in range(ilo[0],ihi[0]+1):
        for cz in range(ilo[1],ihi[1]+1):OFFSET_BUCKETS.setdefault((cx,cz),[]).append(i)
def cross2(a,b):return a[...,0]*b[...,1]-a[...,1]*b[...,0]
def rear_points(xz):
    """Return posterior head point, oriented normal, source triangle id.

    This uses existing anatomical triangle connectivity. A projected-center
    KD tree locates candidate triangles; actual barycentric containment and
    Y interpolation establish exact ray hits. Failed hits expand candidates.
    """
    xz=np.asarray(xz,float).reshape(-1,2);points=np.full((len(xz),3),np.nan);normals=points.copy();ids=np.full(len(xz),-1)
    unresolved=np.arange(len(xz))
    for k in [24,80,256,1024]:
        if not len(unresolved):break
        _,candidates=TREE.query(xz[unresolved],k=min(k,len(T)))
        if candidates.ndim==1:candidates=candidates[:,None]
        a,b,c=A[candidates],B[candidates],C[candidates];p=xz[unresolved,None,:]
        determinant=cross2(b-a,c-a)
        bb=np.divide(cross2(p-a,c-a),determinant,out=np.zeros_like(determinant),where=np.abs(determinant)>1e-14)
        cc=np.divide(cross2(b-a,p-a),determinant,out=np.zeros_like(determinant),where=np.abs(determinant)>1e-14)
        inside=(np.abs(determinant)>1e-14)&(bb>=-1e-9)&(cc>=-1e-9)&(bb+cc<=1+1e-9)
        y=T[candidates,0,1]*(1-bb-cc)+T[candidates,1,1]*bb+T[candidates,2,1]*cc
        y[~inside]=-np.inf;which=y.argmax(1);hit=np.isfinite(y[np.arange(len(y)),which])
        ri=unresolved[hit];ci=candidates[np.arange(len(y))[hit],which[hit]]
        points[ri]=np.column_stack([xz[ri,0],y[np.arange(len(y))[hit],which[hit]],xz[ri,1]])
        bbh=bb[np.arange(len(y))[hit],which[hit]];cch=cc[np.arange(len(y))[hit],which[hit]]
        weights=np.stack([1-bbh-cch,bbh,cch],axis=1)
        normals[ri]=(vertex_normal[F[IDS[ci]]]*weights[:,:,None]).sum(1)
        normals[ri]/=np.maximum(np.linalg.norm(normals[ri],axis=1)[:,None],1e-15)
        normals[ri[normals[ri,1]<0]]*=-1
        ids[ri]=IDS[ci];unresolved=unresolved[~hit]
    return points,normals,ids
def offset_rear_points(target_xz,distance,iterations=30):
    """Exact posterior ray hit on the anatomical triangle-offset level.

    Original triangle faces offset by distance, original edges expanded into
    capsules, and original vertices expanded into spheres cover the complete
    distance offset. Maximum +Y ray intersection gives the posterior envelope.
    This avoids inverted normal-parameter maps around ear-root concavities.
    """
    assert 0<distance<=3.5
    targets=np.asarray(target_xz,float).reshape(-1,2)
    world=np.full((len(targets),3),np.nan);normals=world.copy();source=np.full(len(targets),-1)
    for begin in range(0,len(targets),192):
        Q=targets[begin:begin+192];lists=[OFFSET_BUCKETS.get(tuple(np.floor(p/OFFSET_CELL).astype(int)),[]) for p in Q]
        counts=np.array([len(a) for a in lists]);qi=np.repeat(np.arange(len(Q)),counts)
        if not len(qi):continue
        ci=np.concatenate(lists);XZ=Q[qi];CT=T[ci];P0=np.column_stack([XZ[:,0],np.zeros(len(XZ)),XZ[:,1]])
        besty=np.full(len(Q),-np.inf);bestfoot=np.zeros((len(Q),3));bestface=np.full(len(Q),-1)
        def offer(y,foot,valid):
            y=np.where(valid,y,-np.inf);local=np.full(len(Q),-np.inf);np.maximum.at(local,qi,y)
            winner=np.full(len(Q),len(qi),dtype=int);match=np.isfinite(y)&(y==local[qi]);np.minimum.at(winner,qi[match],np.flatnonzero(match))
            good=np.isfinite(local)&(local>besty);where=np.flatnonzero(good);chosen=winner[good]
            besty[where]=local[where];bestfoot[where]=foot[chosen];bestface[where]=ci[chosen]
        # Face parallel plane, foot barycentric containment in original triangle.
        cn=N[ci].copy();cn[cn[:,1]<0]*=-1
        pd=(cn*CT[:,0]).sum(1)
        y=np.divide(pd+distance-cn[:,0]*XZ[:,0]-cn[:,2]*XZ[:,1],cn[:,1],out=np.zeros(len(ci)),where=np.abs(cn[:,1])>1e-13)
        point=P0.copy();point[:,1]=y;foot=point-distance*cn
        aa,bb,cc=CT[:,0,:][:,[0,2]],CT[:,1,:][:,[0,2]],CT[:,2,:][:,[0,2]]
        det=cross2(bb-aa,cc-aa);pp=foot[:,[0,2]]
        fb=np.divide(cross2(pp-aa,cc-aa),det,out=np.zeros(len(ci)),where=np.abs(det)>1e-13)
        fc=np.divide(cross2(bb-aa,pp-aa),det,out=np.zeros(len(ci)),where=np.abs(det)>1e-13)
        valid=(np.abs(cn[:,1])>1e-13)&(np.abs(det)>1e-13)&(fb>=-1e-10)&(fc>=-1e-10)&(fb+fc<=1+1e-10)
        offer(y,foot,valid)
        # Exact upper roots of finite edge cylinders.
        for a,b in [(0,1),(1,2),(2,0)]:
            A0=CT[:,a];U=CT[:,b]-A0;u2=(U*U).sum(1);W=P0-A0;dot=(W*U).sum(1)
            alpha=1-U[:,1]**2/u2;beta=2*(W[:,1]-U[:,1]*dot/u2);gamma=(W*W).sum(1)-dot**2/u2-distance**2
            disc=beta**2-4*alpha*gamma
            y=np.divide(-beta+np.sqrt(np.maximum(disc,0)),2*alpha,out=np.zeros(len(ci)),where=np.abs(alpha)>1e-13)
            parameter=(dot+y*U[:,1])/u2;foot=A0+parameter[:,None]*U
            offer(y,foot,(alpha>1e-13)&(disc>=-1e-10)&(parameter>=-1e-10)&(parameter<=1+1e-10))
        # Original vertex spheres.
        for j in range(3):
            foot=CT[:,j];rad=distance**2-(XZ[:,0]-foot[:,0])**2-(XZ[:,1]-foot[:,2])**2
            y=foot[:,1]+np.sqrt(np.maximum(rad,0));offer(y,foot,rad>=-1e-10)
        world[begin:begin+len(Q)]=np.column_stack([Q[:,0],besty,Q[:,1]])
        normals[begin:begin+len(Q)]=(world[begin:begin+len(Q)]-bestfoot)/distance
        source[begin:begin+len(Q)]=np.where(bestface>=0,IDS[np.maximum(bestface,0)],-1)
    return world,normals,source,np.zeros(len(targets))
if __name__=='__main__':
    import json
    queries=np.array([[x,z] for z in [8.2,20.,26.2,39.2,52.2,55.2] for x in [-72.8,-66.8,-60.8,-50.,0.,50.,60.8,66.8,72.8]])
    p,n,ids=rear_points(queries)
    rows=[{'query_xz_mm':q.tolist(),'point_xyz_mm':a.tolist(),'normal':b.tolist(),'source_face':int(i)} for q,a,b,i in zip(queries,p,n,ids)]
    (HERE/'rear_surface_queries.json').write_text(json.dumps(rows,indent=2),encoding='utf-8')
    print(json.dumps(rows,indent=2))
