"""Sampled free-center connectivity of the camera-hull sphere witness.

A rigid, taut band is assumed. This grid check corroborates the aperture
argument; it does not certify flexible strap mechanics or arbitrary motion.
"""
from pathlib import Path
from collections import deque
import hashlib,json,time
import numpy as np
import manifold3d as md
import vtk
from vtk.util.numpy_support import numpy_to_vtk,numpy_to_vtkIdTypeArray

P=Path(__file__).resolve().parents[1];G=P/'geometry'
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def solid(q):return md.Manifold(md.Mesh64(vert_properties=np.ascontiguousarray(q['v'],dtype=np.float64),tri_verts=np.ascontiguousarray(q['f'],dtype=np.uint64)))
def main():
    begin=time.time();paths=[G/(s+'.npz') for s in ['front_body','camera','retention_band']]+[G/'geometry_values.json']
    hashes={str(p.relative_to(P)).replace('\\','/'):digest(p) for p in paths}
    values=json.loads(paths[-1].read_text());tf=np.array(values['camera_transform_native_to_wearing'])
    center=np.array([0.,0.,-12.5])@tf[:,:3].T+tf[:,3]
    q=np.load(G/'camera.npz');pts=q['v'][np.unique(q['f'])];hull=md.Manifold.hull_points(pts)
    hm=hull.to_mesh64();hv=np.asarray(hm.vert_properties)[:,:3];tr=hv[np.asarray(hm.tri_verts)]
    n=np.cross(tr[:,1]-tr[:,0],tr[:,2]-tr[:,0]);n/=np.linalg.norm(n,axis=1)[:,None]
    radius=float(np.einsum('ij,ij->i',n,tr[:,0]-center).min())
    obstacle=solid(np.load(G/'front_body.npz'))+solid(np.load(G/'retention_band.npz'))
    mesh=obstacle.to_mesh64();v=np.asarray(mesh.vert_properties)[:,:3];f=np.asarray(mesh.tri_verts)
    vp=vtk.vtkPoints();vp.SetData(numpy_to_vtk(np.ascontiguousarray(v),deep=True))
    cells=vtk.vtkCellArray();cells.ImportLegacyFormat(numpy_to_vtkIdTypeArray(np.ascontiguousarray(np.column_stack([np.full(len(f),3),f]).ravel(),dtype=np.int64),deep=True))
    pd=vtk.vtkPolyData();pd.SetPoints(vp);pd.SetPolys(cells)
    implicit=vtk.vtkImplicitPolyDataDistance();implicit.SetInput(pd)
    step=2.;axes=[center[i]+step*np.arange(a,b+1) for i,(a,b) in enumerate([(-40,40),(-20,35),(-20,25)])]
    grid=np.stack(np.meshgrid(*axes,indexing='ij'),-1);flat=grid.reshape(-1,3)
    ds=np.fromiter((implicit.EvaluateFunction(tuple(p)) for p in flat),float,count=len(flat)).reshape(grid.shape[:3])
    # The source floor/sphere nominal contact has <0.0001 mm tessellation error.
    tolerance=.0001;free=ds>=radius-tolerance;seed=(40,20,20)
    assert np.linalg.norm(grid[seed]-center)<1e-10
    reached=np.zeros(free.shape,dtype=bool);todo=deque([seed]);reached[seed]=True;boundary=[]
    if free[seed]:
        while todo:
            p=todo.popleft()
            if any(p[i] in [0,free.shape[i]-1] for i in range(3)):boundary.append(p)
            for axis in range(3):
                for sign in [-1,1]:
                    nxt=list(p);nxt[axis]+=sign;nxt=tuple(nxt)
                    if all(0<=nxt[i]<free.shape[i] for i in range(3)) and free[nxt] and not reached[nxt]:
                        reached[nxt]=True;todo.append(nxt)
    reached_points=grid[reached]
    unchanged=all(digest(P/name)==sha for name,sha in hashes.items())
    out={'source_sha256':hashes,'source_changed_during_run':not unchanged,'sphere_center_wearing_mm':center.tolist(),'sphere_radius_mm':radius,
         'sampled_grid_pitch_mm':step,'sampled_grid_bounds_xyz_mm':[flat.min(0).tolist(),flat.max(0).tolist()],
         'center_free':bool(free[seed]),'center_obstacle_distance_mm':float(ds[seed]),'radius_contact_tolerance_mm':tolerance,
         'reachable_center_samples':int(reached.sum()),'reachable_bounds_xyz_mm':[reached_points.min(0).tolist(),reached_points.max(0).tolist()],
         'reachable_grid_boundary_samples':len(boundary),'sampled_enclosed_component':bool(free[seed] and not boundary and unchanged),
         'interpretation':'Sampled 2 mm free-center connectivity with the printed body and a rigid taut-band reference. A 25 mm sphere is a witness inside the exact camera convex hull; upper and lower rear apertures are smaller than its diameter.',
         'limitations':['A lattice flood is corroborating evidence, not continuous configuration-space topology or a proof of arbitrary camera motion.','The textile reference is treated as rigid and correctly cinched; closure strength, stretch and physical hand flips are untested.'],
         'runtime_seconds':time.time()-begin}
    (P/'checks/retention_sphere.json').write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
if __name__=='__main__':main()
