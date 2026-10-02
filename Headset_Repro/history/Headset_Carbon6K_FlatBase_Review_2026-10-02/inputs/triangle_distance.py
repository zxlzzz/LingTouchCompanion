"""Continuous triangle-mesh distance using all closest/intersection features.

Input triangles may be open surfaces. No ellipsoid, convex-hull or vertex-only
distance replaces the original anatomical mesh.
"""
import numpy as np

def closest_points(P,A,B,C):
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

def segment_triangle(P0,P1,A,B,C):
    P0,P1,A,B,C=np.broadcast_arrays(P0,P1,A,B,C)
    direction=P1-P0;e1=B-A;e2=C-A
    h=np.cross(direction,e2);det=(e1*h).sum(-1)
    inv=np.divide(1.,det,out=np.zeros_like(det),where=np.abs(det)>1e-13)
    s=P0-A;u=inv*(s*h).sum(-1);q=np.cross(s,e1)
    v=inv*(direction*q).sum(-1);t=inv*(e2*q).sum(-1)
    ok=(np.abs(det)>1e-13)&(u>=-1e-12)&(v>=-1e-12)&(u+v<=1+1e-12)&(t>=-1e-12)&(t<=1+1e-12)
    return ok,P0+t[...,None]*direction

def min_triangle_distance(head_tri,case_tri):
    """Return distance and nose/case witness points, with triangle indexes."""
    HALL=np.asarray(head_tri,float);K=np.asarray(case_tri,float)
    best=[float('inf'),None,None,None,None]
    # A nearest original-vertex pair is a valid surface-distance upper bound.
    # Use it to prune triangle pairs only by rigorous AABB lower bounds.
    from scipy.spatial import cKDTree
    hp=HALL.reshape(-1,3);kp=K.reshape(-1,3)
    distances,nearest=cKDTree(hp).query(kp)
    vi=int(np.argmin(distances));hvi=int(nearest[vi])
    best[:]=[float(distances[vi]),hp[hvi].copy(),kp[vi].copy(),hvi//3,vi//3]
    head_lo,head_hi=HALL.min(1),HALL.max(1)
    def offer(ds,p,q,case_i,head_ids=None):
        i=int(np.argmin(ds));distance=float(ds[i])
        if distance<best[0]:
            best[:]=[distance,p[i].copy(),q[i].copy(),int(head_ids[i]) if head_ids is not None else i,case_i]
    for ci,C in enumerate(K):
        gap=np.maximum(np.maximum(head_lo-C.max(0),C.min(0)-head_hi),0.)
        possible=(gap*gap).sum(1)<=(best[0]+1e-10)**2
        ids=np.flatnonzero(possible)
        if not len(ids):continue
        H=HALL[ids];head_vertices=H.reshape(-1,3)
        Q=closest_points(head_vertices,C[0],C[1],C[2]);offer(np.linalg.norm(head_vertices-Q,axis=-1),head_vertices,Q,ci,np.repeat(ids,3))
        for p in C:
            P=np.broadcast_to(p,(len(H),3));Q=closest_points(P,H[:,0],H[:,1],H[:,2]);offer(np.linalg.norm(P-Q,axis=-1),Q,P,ci,ids)
        for a,b in [(0,1),(1,2),(2,0)]:
            hp,hq=H[:,a],H[:,b]
            ok,I=segment_triangle(hp,hq,C[0],C[1],C[2])
            if ok.any():i=int(np.flatnonzero(ok)[0]);return [0.,I[i],I[i],int(ids[i]),ci]
            for c,d in [(0,1),(1,2),(2,0)]:
                cp,cq=C[c],C[d]
                ok,I=segment_triangle(cp,cq,H[:,0],H[:,1],H[:,2])
                if ok.any():i=int(np.flatnonzero(ok)[0]);return [0.,I[i],I[i],int(ids[i]),ci]
                u=hq-hp;v=cq-cp;w=hp-cp
                aa=(u*u).sum(-1);bb=(u*v).sum(-1);cc=float(v@v);dd=(u*w).sum(-1);ee=(v*w).sum(-1)
                den=aa*cc-bb*bb
                s=np.divide(bb*ee-cc*dd,den,out=np.zeros(len(H)),where=np.abs(den)>1e-20)
                t=np.divide(aa*ee-bb*dd,den,out=np.zeros(len(H)),where=np.abs(den)>1e-20)
                valid=(np.abs(den)>1e-20)&(s>=0)&(s<=1)&(t>=0)&(t<=1)
                pp=hp+s[:,None]*u;qq=cp+t[:,None]*v
                ds=np.linalg.norm(pp-qq,axis=-1);ds[~valid]=np.inf
                if valid.any():offer(ds,pp,qq,ci,ids)
    return best

def clip_triangles_y_negative(vertices,faces,limit=0.):
    """Y<=limit clipping, retaining source faces; wholly-boundary faces excluded."""
    triangles=np.asarray(vertices)[np.asarray(faces)]
    out=[];source=[]
    for fi,tri in enumerate(triangles):
        if tri[:,1].min()>=limit:continue
        poly=[];a=tri[-1];da=a[1]-limit
        for b in tri:
            db=b[1]-limit
            if (da<=0)!=(db<=0):poly.append(a+(b-a)*da/(da-db))
            if db<=0:poly.append(b)
            a,da=b,db
        for j in range(1,len(poly)-1):out.append([poly[0],poly[j],poly[j+1]]);source.append(fi)
    return np.asarray(out),np.asarray(source)
