"""Verify original-head clearance over complete triangular rear surfaces."""
from pathlib import Path
import json, sys, time, hashlib
import numpy as np
from scipy.spatial import cKDTree
from rear_surface import V, F, T, IDS, OFFSET_BUCKETS, OFFSET_CELL, HEAD_SOURCE

HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[1]/'Headset_FullCase_30mm_Preview_2026-10-02/headform'))
from triangle_distance import closest_points

def pair_distance(H,C):
    """Exact triangle-pair distance for known disjoint surfaces, all features."""
    best=np.full(len(H),np.inf);pbest=np.zeros((len(H),3));qbest=pbest.copy()
    def offer(p,q,valid=None):
        ds=((p-q)**2).sum(1)
        if valid is not None:ds[~valid]=np.inf
        use=ds<best
        best[use]=ds[use];pbest[use]=p[use];qbest[use]=q[use]
    for j in range(3):
        p=H[:,j];q=closest_points(p,C[:,0],C[:,1],C[:,2]);offer(p,q)
        q=C[:,j];p=closest_points(q,H[:,0],H[:,1],H[:,2]);offer(p,q)
    for a,b in [(0,1),(1,2),(2,0)]:
        hp,hq=H[:,a],H[:,b];u=hq-hp
        for c,d in [(0,1),(1,2),(2,0)]:
            cp,cq=C[:,c],C[:,d];v=cq-cp;w=hp-cp
            aa=(u*u).sum(1);bb=(u*v).sum(1);cc=(v*v).sum(1);dd=(u*w).sum(1);ee=(v*w).sum(1)
            den=aa*cc-bb*bb
            s=np.divide(bb*ee-cc*dd,den,out=np.zeros(len(H)),where=np.abs(den)>1e-20)
            t=np.divide(aa*ee-bb*dd,den,out=np.zeros(len(H)),where=np.abs(den)>1e-20)
            valid=(np.abs(den)>1e-20)&(s>=0)&(s<=1)&(t>=0)&(t<=1)
            offer(hp+s[:,None]*u,cp+t[:,None]*v,valid)
    return np.sqrt(best),pbest,qbest

def point_head_distance(points,batchsize=192):
    distances=np.full(len(points),np.inf);witness=np.zeros_like(points);face=np.full(len(points),-1)
    for start in range(0,len(points),batchsize):
        P=points[start:start+batchsize]
        lists=[OFFSET_BUCKETS.get(tuple(np.floor(p[[0,2]]/OFFSET_CELL).astype(int)),[]) for p in P]
        count=np.array([len(a) for a in lists]);pi=np.repeat(np.arange(len(P)),count)
        hi=np.concatenate(lists)
        H=T[hi];Q=closest_points(P[pi],H[:,0],H[:,1],H[:,2]);ds=((P[pi]-Q)**2).sum(1)
        best=np.full(len(P),np.inf);np.minimum.at(best,pi,ds)
        which=np.full(len(P),len(pi),int);matched=ds==best[pi];np.minimum.at(which,pi[matched],np.flatnonzero(matched))
        distances[start:start+len(P)]=np.sqrt(best);witness[start:start+len(P)]=Q[which];face[start:start+len(P)]=IDS[hi[which]]
    return distances,witness,face

def minimum_surfaces(source,case,padding=3.5):
    """Continuous min with conservative spatial buckets then exact features."""
    SV,SF=source;CV,CF=case;H=SV[SF];C=CV[CF]
    vd,vi=cKDTree(SV).query(CV);ci=int(np.argmin(vd));hi=int(vi[ci]);best=[float(vd[ci]),SV[hi],CV[ci],-1,-1]
    hlo,hhi=H.min(1),H.max(1);cell=2.;buckets={}
    for fi,(lo,upper) in enumerate(zip(H[:,:,[0,2]].min(1)-padding,H[:,:,[0,2]].max(1)+padding)):
        il,iu=np.floor(lo/cell).astype(int),np.floor(upper/cell).astype(int)
        for x in range(il[0],iu[0]+1):
            for z in range(il[1],iu[1]+1):buckets.setdefault((x,z),[]).append(fi)
    tested=0;candidate_count=0
    for start in range(0,len(C),96):
        K=C[start:start+96];cent=K.mean(1)
        lists=[buckets.get(tuple(np.floor(p[[0,2]]/cell).astype(int)),[]) for p in cent]
        counts=np.array([len(a) for a in lists]);caseids=np.repeat(np.arange(len(K)),counts)
        headids=np.concatenate(lists);candidate_count+=len(headids)
        gap=np.maximum(np.maximum(hlo[headids]-K[caseids].max(1),K[caseids].min(1)-hhi[headids]),0.)
        keep=(gap*gap).sum(1)<=(best[0]+1e-10)**2
        headids=headids[keep];caseids=caseids[keep]
        for chunk in range(0,len(headids),16000):
            hh,kk=headids[chunk:chunk+16000],caseids[chunk:chunk+16000]
            ds,p,q=pair_distance(H[hh],K[kk]);tested+=len(ds)
            if len(ds):
                wi=int(np.argmin(ds))
                if ds[wi]<best[0]:best=[float(ds[wi]),p[wi],q[wi],int(hh[wi]),start+int(kk[wi])]
        if start%9600==0:print('continuous pairs',start,'/',len(C),'current minimum',best[0],flush=True)
    return {'distance_mm':best[0],'source_witness_xyz_mm':best[1].tolist(),'case_witness_xyz_mm':best[2].tolist(),'source_face_index':best[3],'case_face_index':best[4],'bbox_candidate_pairs':candidate_count,'exact_pairs_evaluated':tested,'spatial_hash_padding_mm':padding,'method':'All vertex-face and interior edge-edge closest features; disjointness independently certified by source-head distance bands.'}

def main():
    begun=time.perf_counter();I=np.load(HERE/'rear_inner_surface.npz');O=np.load(HERE/'rear_outer_surface.npz');IV,IF=I['v'],I['f'];OV,OF=O['v'],O['f']
    report={'preview_only':True,'head_source':str(HEAD_SOURCE),'registration_unchanged':True,'head_scale':1.,'wearing_status':'Original BTTF/head trial still fails; this validates posterior new-tray surface only.'}
    vertex_records={}
    for name,P,Faces,nominal in [('inner',IV,IF,1.),('outer',OV,OF,3.5)]:
        ds,wp,ids=point_head_distance(P);imin=int(ds.argmin());imax=int(ds.argmax())
        edge=float(np.linalg.norm(P[Faces]-np.roll(P[Faces],1,axis=1),axis=2).max());radius=edge/np.sqrt(3)
        # Distance to a closed surface is1-Lipschitz. Every triangle point lies
        # within max-edge/sqrt(3) of one of its vertices (tight for equilateral).
        bound=[float(ds.min()-radius),float(ds.max()+radius)]
        vertex_records[name]={'nominal_original_head_distance_mm':nominal,'actual_vertex_min_mm':float(ds.min()),'actual_vertex_max_mm':float(ds.max()),'min_vertex_xyz_mm':P[imin].tolist(),'min_head_witness_xyz_mm':wp[imin].tolist(),'min_head_face_index':int(ids[imin]),'max_vertex_xyz_mm':P[imax].tolist(),'max_head_witness_xyz_mm':wp[imax].tolist(),'max_head_face_index':int(ids[imax]),'max_triangle_edge_mm':edge,'rigorous_triangle_vertex_cover_radius_mm':float(radius),'continuous_entire_surface_distance_bound_mm':bound,'certificate':'1-Lipschitz original-triangle distance; each surface vertex independently queried against all potentially nearer anatomical head triangles, including edges and faces. Every point of every triangle is within maxedge/sqrt(3) of a vertex. Head faces excluded from posterior buckets have Y<=110 or wholly outside Z−3.5..58.7 and cannot be closer than distances reported.'}
        print(name,'vertices',len(P),'nearest distance',float(ds.min()),float(ds.max()),'continuous bound',bound,flush=True)
    report['head_clearance']=vertex_records
    report['inner_entire_surface_0_to_2_pass']=vertex_records['inner']['continuous_entire_surface_distance_bound_mm'][0]>=0 and vertex_records['inner']['continuous_entire_surface_distance_bound_mm'][1]<=2
    report['continuous_inner_outer_disjoint_lower_bound_mm']=vertex_records['outer']['continuous_entire_surface_distance_bound_mm'][0]-vertex_records['inner']['continuous_entire_surface_distance_bound_mm'][1]
    # Conservative padding covers any closer source triangle: case centroid
    # to any case point <=2*maxedge/3<.8, valid vertex upper bound near2.5.
    report['actual_inner_outer_min_distance']=minimum_surfaces((IV,IF),(OV,OF))
    report['wall_nominal_mm']=2.5
    report['wall_interpretation']='Exact smooth level separation2.5mm before triangular tessellation; actual closest separation of the delivered triangular surfaces measured continuously above. No tolerance was silently added.'
    report['fingerprints_sha256']={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in [HERE/'rear_tray.npz',HERE/'rear_inner_surface.npz',HERE/'rear_outer_surface.npz']}
    report['elapsed_seconds']=time.perf_counter()-begun
    (HERE/'rear_actual_clearance.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
