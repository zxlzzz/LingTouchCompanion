"""Independent actual-STEP camera fit, aperture and removal checks.

Uses convex hulls only as conservative occupied volumes: the actual STEP
triangles remain the reference and every physical part must lie in the hull.
The source is open, so treating it as a watertight Boolean camera would be
incorrect. A positive conservative hull clearance proves its enclosed actual
triangles do not intersect the shell material.
"""
from pathlib import Path
import json,hashlib,time,sys
import numpy as np
import manifold3d as md
import vtk
from vtk.util.numpy_support import numpy_to_vtk,numpy_to_vtkIdTypeArray

P=Path(__file__).resolve().parents[1];G=P/'geometry';M=md.Manifold
def load(name):
    q=np.load(G/(name+'.npz'));return q
def solid(q):
    m=M(md.Mesh64(vert_properties=np.ascontiguousarray(q['v'],dtype=np.float64),tri_verts=np.ascontiguousarray(q['f'],dtype=np.uint64)))
    assert m.status()==md.Error.NoError,m.status();return m
def polydata(v,f):
    p=vtk.vtkPoints();p.SetData(numpy_to_vtk(np.ascontiguousarray(v),deep=True))
    cells=vtk.vtkCellArray();n=len(f);conn=np.column_stack([np.full(n,3),f]).ravel()
    cells.SetCells(n,numpy_to_vtkIdTypeArray(np.ascontiguousarray(conn,dtype=np.int64),deep=True))
    out=vtk.vtkPolyData();out.SetPoints(p);out.SetPolys(cells);return out
def nearest(v,target):
    locator=vtk.vtkStaticCellLocator();locator.SetDataSet(polydata(target['v'],target['f']));locator.BuildLocator()
    cp=[0.,0.,0.];cid=vtk.reference(0);sid=vtk.reference(0);d2=vtk.reference(0.)
    dist=np.empty(len(v));closest=np.empty_like(v)
    for i,p in enumerate(v):
        locator.FindClosestPoint(p,cp,cid,sid,d2);dist[i]=float(d2)**.5;closest[i]=cp
    return dist,closest
def points_inside(v,m):
    # Oblique finite rays avoid alignment with planar triangle diagonals.
    counts=np.array([len(m.ray_cast(tuple(p),tuple(p+np.array([400,.137,.219])))) for p in v])
    return counts%2==1
def mesh_state(m):
    a=m.to_mesh64();v=np.asarray(a.vert_properties)[:,:3];f=np.asarray(a.tri_verts)
    return {'v':v,'f':f}
def section_points(v,f,z):
    tri=v[f];delta=tri[:,:,2]-z
    tri=tri[(delta.min(1)<0)&(delta.max(1)>0)]
    pts=[]
    for a,b in [(0,1),(1,2),(2,0)]:
        aa=tri[:,a];bb=tri[:,b];cross=(aa[:,2]<z)!=(bb[:,2]<z)
        aa=aa[cross];bb=bb[cross];t=(z-aa[:,2])/(bb[:,2]-aa[:,2])
        pts.append(aa+t[:,None]*(bb-aa))
    return np.unique(np.round(np.concatenate(pts),8),axis=0)
def nominal_fov_check(body,transform):
    # Read optical simulation geometry separately: it is never a physical
    # camera part and never contributes to camera fit or occupied volume.
    sys.path.insert(0,str(P));import camera_source as source
    reader=source.STEPControl_Reader();assert reader.ReadFile(str(source.SOURCE))==source.IFSelect_RetDone
    reader.TransferRoots();parts=[p for top in source.children(reader.OneShape()) for p in source.children(top)]
    result=[]
    for ident,name in [(63,'RGB'),(62,'TX'),(23,'RX')]:
        v,f=source.tessellate(parts[ident]);sections=[]
        wear_all=v@transform[:,:3].T+transform[:,3]
        beam_hull=M.hull_points(wear_all)
        overlap=float((beam_hull^body).volume())
        min_gap=float(beam_hull.min_gap(body,5))
        for z in [.8001,1.1,1.4,1.7,1.9999,2.4,2.8,3.2,3.6,4.0,4.3999]:
            native=section_points(v,f,z)
            wear=native@transform[:,:3].T+transform[:,3]
            inside=points_inside(wear,body)
            sections.append({'native_front_z_mm':z,'wearing_y_mm':float(wear[0,1]),'native_section_xy_bounds_mm':[native[:,:2].min(0).tolist(),native[:,:2].max(0).tolist()],'boundary_points_in_shell_material':int(inside.sum()),'point_count':len(wear),'blocked_examples_mm':wear[inside][:4].tolist()})
        result.append({'name':name,'source_virtual_part_id':ident,'conservative_full_source_beam_hull_shell_overlap_mm3':overlap,'complete_source_beam_lower_bound_gap_mm':min_gap,'sections':sections,'all_sampled_sections_clear':all(x['boundary_points_in_shell_material']==0 for x in sections),'full_conservative_source_beam_clear':overlap<1e-6 and min_gap>0})
    return result
def main():
    names=['camera','front_body','service_lid','bezel_trim','cable_gland','fasteners']
    start=time.time();source_hashes={name:hashlib.sha256((G/(name+'.npz')).read_bytes()).hexdigest() for name in names}
    camera=load('camera');v=np.unique(np.round(camera['v'],8),axis=0)
    vals=json.loads((G/'geometry_values.json').read_text());transform=np.array(vals['camera_transform_native_to_wearing'])
    native=np.load(P/'inputs/camera_physical_native.npz')
    expected=native['v']@transform[:,:3].T+transform[:,3]
    transform_error=float(np.max(np.abs(expected-camera['v'])))
    assert transform_error<1e-8,'Wearing camera differs from unchanged native source'
    assert np.allclose(transform,[[1,0,0,-.0290536247],[0,0,-1,-30],[0,1,0,35.5]]), 'Update axial optical audit for changed camera pose'
    bodyq=load('front_body');lidq=load('service_lid');body=solid(bodyq);lid=solid(lidq)
    trim=solid(load('bezel_trim'));gland=solid(load('cable_gland'));fasteners=solid(load('fasteners'))
    optical_shell=body+trim
    closed=body+lid+trim+gland+fasteners;closedq=mesh_state(closed)
    camhull=M.hull_points(v)
    assert camhull.status()==md.Error.NoError
    body_overlap=(camhull^body).volume();lid_overlap=(camhull^lid).volume()
    hull_gap=camhull.min_gap(closed,10)
    ins=points_inside(v,closed)
    # All source vertices plus facet centroids: exact nearest point on shell triangles.
    sample=np.vstack([v,camera['v'][camera['f']].mean(1)])
    d,cp=nearest(sample,closedq)
    k=d.argmin()
    regions={'front':sample[:,1]<-29.5,'rear':sample[:,1]>-5.05,
             'roof':sample[:,2]>51,'bottom':sample[:,2]<24.5,
             'left':sample[:,0]<-38,'right':sample[:,0]>38}
    regional={}
    for name,mask in regions.items():
        ids=np.flatnonzero(mask);kk=ids[np.argmin(d[ids])]
        regional[name]={'sample_count':int(len(ids)),'sampled_actual_camera_to_shell_min_mm':float(d[kk]),'camera_point_mm':sample[kk].tolist(),'shell_closest_point_mm':cp[kk].tolist()}
    # A continuous convex extrusion along +Y bounds every actual point throughout.
    removal=M.batch_hull([camhull,camhull.translate((0,80,0))])
    removal_overlap=(removal^body).volume()
    removal_gap=removal.min_gap(body,10)
    # Check each optical front-face vertex ray toward −Y through both actual walls.
    optical=[];pid=camera['part'];faces=camera['f'];cv=camera['v']
    for ident,name in [(0,'RGB'),(1,'RX'),(2,'TX')]:
        ids=np.unique(faces[pid==ident]);vv=cv[ids]
        front=vv[np.abs(vv[:,1]+29)<1e-6]
        if name=='TX':
            # Actual active planar window bounds; do not check mechanical flange.
            front=front[(front[:,0]>=3.5-.0290536247-1e-6)&(front[:,0]<=10.5-.0290536247+1e-6)&(front[:,2]>=33.25-1e-6)&(front[:,2]<=37.75+1e-6)]
        blocked=[]
        for p in front:
            hh=optical_shell.ray_cast(tuple(p),tuple(p+[0,-15,0]))
            if hh:blocked.append({'point':p.tolist(),'first_hit':hh[0].position})
        centerx={0:-22,1:22,2:7}[ident]-.0290536247
        optical.append({'name':name,'measured_center_wearing_mm':[centerx,-29,35.5],'front_face_sample_vertices':len(front),'blocked_axial_vertices':len(blocked),'blocked_examples':blocked[:8]})
    # Camera is enclosed when viewed from below and either side. Rays originate
    # on every actual source surface vertex, including glass and internal bodies.
    exposure=[]
    for name,direction in [('bottom',(0,0,-1)),('left',(-1,0,0)),('right',(1,0,0))]:
        vector=np.array(direction)*200;uncovered=[]
        for p in v:
            if not closed.ray_cast(tuple(p),tuple(p+vector)):uncovered.append(p.tolist())
        exposure.append({'view':name,'actual_camera_vertices_with_unblocked_ray':len(uncovered),'examples':uncovered[:8]})
    # Six translations demonstrate physical walls intercept escape in all axes.
    blockers=[]
    for direction in [(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)]:
        vector=np.array(direction)*50;sweep=M.batch_hull([camhull,camhull.translate(tuple(vector))])
        blockers.append({'direction':list(direction),'shell_material_crossed_volume_mm3':float((sweep^closed).volume())})
    fov=nominal_fov_check(optical_shell,transform)
    # These are an explicit design-size allowance, not a measured real cable.
    proxy_parts=[('metal_nose',[-39,-12.6,34.3],[-35.8,-4.4,36.7]),
                 ('molded_body',[-52,-13.5,31.5],[-39,-3.5,39.5])]
    plug=[]
    for name,lo,hi in proxy_parts:
        lo=np.array(lo);hi=np.array(hi);proxy=M.cube(tuple(hi-lo)).translate(tuple(lo))
        overlap=float((proxy^closed).volume());gap=float(proxy.min_gap(closed,5))
        clashes=[]
        for label,target in [('front_body',body),('service_lid',lid),('bezel_trim',trim),('cable_gland',gland),('fasteners',fasteners),('service_lip_diagnostic_subset',solid(load('service_lip')))]:
            clash=proxy^target;volume=float(clash.volume())
            if volume>1e-8:
                clashes.append({'part':label,'overlap_volume_mm3':volume,'overlap_bounds_xyz_mm':list(clash.bounding_box())})
        plug.append({'name':name,'bounds_xyz_mm':[lo.tolist(),hi.tolist()],'size_xyz_mm':(hi-lo).tolist(),'shell_and_lid_overlap_mm3':overlap,'minimum_shell_clearance_mm':gap,'clashes':clashes,'pass':overlap<1e-6 and gap>0})
    out={'source_sha256':source_hashes,
         'source_changed_during_run':any(hashlib.sha256((G/(name+'.npz')).read_bytes()).hexdigest()!=digest for name,digest in source_hashes.items()),
         'actual_camera_reference_vertices':len(v),'actual_camera_reference_triangles':len(camera['f']),
         'wearing_vs_transformed_native_source_max_error_mm':transform_error,
         'physical_step_fov_artifacts_present':any(x in np.unique(pid) for x in [23,62,63]),
         'physical_assembly_parts_checked':names[1:],
         'fit':{'conservative_camera_hull_intersection_body_mm3':float(body_overlap),'conservative_camera_hull_intersection_lid_mm3':float(lid_overlap),'actual_reference_vertices_in_shell_material':int(ins.sum()),'complete_triangle_clearance_lower_bound_mm':float(hull_gap),'vertex_centroid_to_actual_shell_upper_bound_mm':float(d[k]),'closest_camera_point_mm':sample[k].tolist(),'closest_shell_point_mm':cp[k].tolist(),'regions':regional},
         'removal_with_lid_removed':{'direction':[0,1,0],'continuous_sweep_length_mm':80,'conservative_sweep_shell_intersection_mm3':float(removal_overlap),'complete_triangle_clearance_lower_bound_mm':float(removal_gap),'pass':removal_overlap<1e-6 and removal_gap>0},
         'optical_front_axis_clipping':optical,
         'source_nominal_fov_sections':fov,
         'usb_plug_design_allowance':{'parts':plug,'camera_socket_overlap_intentionally_not_tested':True,'limitation':'This verifies shell room for the stated slim right-angle connector design envelope; it is not a measurement of a purchased cable or proof of insertion into the camera USB socket.'},
         'bottom_and_side_exposure':exposure,
         'closed_retention':{'six_axis_escape_sweeps':blockers,'pass_closed_six_axes':all(r['shell_material_crossed_volume_mm3']>0 for r in blockers),'reason':'Service lid mechanically closes 96×33.6 mm access opening. Front optical openings are ≤16.5 mm internally; the lower-edge split gland leaves a Ø4.5 mm wire passage after assembly. The bolted lid and installed gland provide physical containment, while adjustable compressible pads establish seating. Six translation tests do not constitute a complete arbitrary-rotation motion proof.'},
         'limitations':['Soft pads intentionally excluded from material collision check; compression and real cable plug fit require physical assembly.','Point and face-centroid closest distances are sampled upper bounds; conservative hull min_gap is a full occupied-triangle lower bound.','Camera source is not watertight. No camera volume Boolean is used.','STEP optical simulation boundary sections are a source-nominal FOV check, not a measured optical certification or a principal-plane calibration. Camera seating repeatability remains dependent on the adjustable pads.'],
         'runtime_seconds':time.time()-start}
    (P/'checks/camera_fit.json').write_text(json.dumps(out,indent=2),encoding='utf8')
    print(json.dumps(out,indent=2))
if __name__=='__main__':main()
