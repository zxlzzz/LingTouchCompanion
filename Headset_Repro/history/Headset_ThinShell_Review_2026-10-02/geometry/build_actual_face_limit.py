"""Forward envelope from original solid, used only to clip added plates."""
from pathlib import Path
import json,time
import numpy as np
import trimesh
import manifold3d as md
P=Path(__file__).resolve().parent;M=md.Manifold
a=np.load(P/'original_reference.npz')
original=M(md.Mesh64(vert_properties=np.ascontiguousarray(a['v'],dtype=np.float64),tri_verts=np.ascontiguousarray(a['f'],dtype=np.uint64)))
region=M.cube((130.02,60.01,55.17567495)).translate((-65.01,-.01,0))
cropped=original^region
t=time.time()
me=cropped.to_mesh64();sv=np.array(me.vert_properties)[:,:3];sf=np.array(me.tri_verts,dtype=int)
normal=np.cross(sv[sf[:,1]]-sv[sf[:,0]],sv[sf[:,2]]-sv[sf[:,0]])
norm=np.linalg.norm(normal,axis=1)
rearfaces=sf[normal[:,1]>norm*1e-12]
used=np.unique(rearfaces);remap=np.full(len(sv),-1,dtype=int);remap[used]=np.arange(len(used))
rv=sv[used];rf=remap[rearfaces];n=len(rv)
vv=np.vstack([rv,rv.copy()]);vv[n:,1]=-120
ff=[*rf.tolist(),*(rf[:,::-1]+n).tolist()]
edges=np.concatenate([rf[:,[0,1]],rf[:,[1,2]],rf[:,[2,0]]])
unique,inverse,counts=np.unique(np.sort(edges,axis=1),axis=0,return_inverse=True,return_counts=True)
boundary=edges[counts[inverse]==1]
for a,b in boundary:ff.extend([[a,b,b+n],[a,b+n,a+n]])
tm=trimesh.Trimesh(vv,np.array(ff),process=True);trimesh.repair.fix_normals(tm,multibody=True)
print(json.dumps({'cropped_triangles':cropped.num_tri(),'rear_triangles':len(rf),'boundary_edges':len(boundary),'watertight':bool(tm.is_watertight)}),flush=True)
limit=M(md.Mesh64(vert_properties=np.ascontiguousarray(tm.vertices,dtype=np.float64),tri_verts=np.ascontiguousarray(tm.faces,dtype=np.uint64)))
assert limit.status()==md.Error.NoError,limit.status()
me=limit.to_mesh64();v=np.array(me.vert_properties)[:,:3];f=np.array(me.tri_verts)
np.savez_compressed(P/'actual_original_forward_limit.npz',v=v,f=f)
report={'method':'Actual original rear-facing triangular surface closed directly toY=-120; source surface coordinates preserved, not sampled rear-coordinate interpolation.','rear_source_triangles':len(rf),'elapsed_seconds':time.time()-t,'triangles':len(f),'volume_mm3':float(limit.volume()),'bounds_xyz_mm':[v.min(0).tolist(),v.max(0).tolist()]}
(P/'actual_original_forward_limit.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report,indent=2))
