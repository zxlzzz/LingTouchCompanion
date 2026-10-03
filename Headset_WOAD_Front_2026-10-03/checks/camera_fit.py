"""Independent prop-camera fit, three-port exposure and cinch-band audit.

The unpowered camera remains unchanged actual STEP triangles. Its convex
hull is used only as a conservative occupied envelope; nominal source FOVs,
USB cables, electrical operation and precise camera fitting are not assumed.
"""
from pathlib import Path
import hashlib,json,time
import numpy as np
import manifold3d as md
import vtk
from vtk.util.numpy_support import numpy_to_vtk,numpy_to_vtkIdTypeArray
import bpy  # Initializes the bundled mathutils module used for head ray tests.
from mathutils.bvhtree import BVHTree
from mathutils import Vector
P=Path(__file__).resolve().parents[1];G=P/'geometry';R=P.parent;M=md.Manifold
TOL=0.001

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(name):return np.load(G/(name+'.npz'))
def solid(q):
    m=M(md.Mesh64(vert_properties=np.ascontiguousarray(q['v'],dtype=np.float64),tri_verts=np.ascontiguousarray(q['f'],dtype=np.uint64)))
    assert m.status()==md.Error.NoError;return m

def nearest(points,q):
    p=vtk.vtkPoints();p.SetData(numpy_to_vtk(np.ascontiguousarray(q['v']),deep=True))
    f=q['f'];cells=vtk.vtkCellArray();conn=np.column_stack([np.full(len(f),3),f]).ravel()
    cells.SetCells(len(f),numpy_to_vtkIdTypeArray(np.ascontiguousarray(conn,dtype=np.int64),deep=True))
    pd=vtk.vtkPolyData();pd.SetPoints(p);pd.SetPolys(cells)
    loc=vtk.vtkStaticCellLocator();loc.SetDataSet(pd);loc.BuildLocator()
    cp=[0.,0.,0.];cid=vtk.reference(0);sid=vtk.reference(0);d2=vtk.reference(0.)
    ds=np.empty(len(points));closest=np.empty_like(points)
    for i,point in enumerate(points):loc.FindClosestPoint(point,cp,cid,sid,d2);ds[i]=float(d2)**.5;closest[i]=cp
    return ds,closest

def diagnostic(clash):
    return [{'volume_mm3':float(m.volume()),'bounds_xyz_mm':list(m.bounding_box())} for m in clash.decompose() if m.volume()>1e-8]

def main():
    start=time.time();files=[G/(n+'.npz') for n in ['front_body','camera','retention_band']]+[G/'geometry_values.json',P/'inputs/camera_physical_native.npz',R/'Headset_Inputs/Medium_Trial_Registered.npz']
    hashes={str(p.relative_to(R)).replace('\\','/'):digest(p) for p in files}
    values=json.loads((G/'geometry_values.json').read_text(encoding='utf8'));tf=np.array(values['camera_transform_native_to_wearing'])
    camera=read('camera');cv=camera['v'];cf=camera['f'];pid=camera['part'];native=np.load(P/'inputs/camera_physical_native.npz')
    error=float(np.max(abs(native['v']@tf[:,:3].T+tf[:,3]-cv)));assert error<1e-8
    assert np.array_equal(cf,native['f']) and np.array_equal(pid,native['part'])
    pts=np.unique(np.round(cv[np.unique(cf)],8),axis=0)
    bodyq=read('front_body');body=solid(bodyq);bandq=read('retention_band');band=solid(bandq);closed=body+band
    camhull=M.hull_points(pts);clash=camhull^body;bandclash=camhull^band;threadclash=band^body
    # A sphere contained in the camera convex hull gives a lower bound on its
    # width in EVERY direction. Matching this to the actual depth upper bound
    # establishes the minimum caliper without only sampling face normals.
    cm=camhull.to_mesh64();ch=np.asarray(cm.vert_properties)[:,:3];ct=ch[np.asarray(cm.tri_verts)]
    normals=np.cross(ct[:,1]-ct[:,0],ct[:,2]-ct[:,0]);normals/=np.linalg.norm(normals,axis=1)[:,None]
    center_native=np.array([0.,0.,-12.5]);center=center_native@tf[:,:3].T+tf[:,3]
    radius=float(np.einsum('ij,ij->i',normals,ct[:,0]-center).min())
    caliper={'inscribed_convex_hull_sphere_center_native_mm':center_native.tolist(),
             'support_plane_sphere_radius_mm':radius,'all_direction_width_lower_bound_mm':2*radius,
             'physical_native_depth_upper_bound_mm':float(np.ptp(native['v'][:,2])),
             'method':'Every oriented hull face lies at least this radius from the center; the enclosed sphere bounds width in every direction. The source physical point set has the same support widths as its convex hull.'}
    sample=np.vstack([pts,cv[cf].mean(1)]);ds,cp=nearest(sample,bodyq);k=ds.argmin()
    bounds=[pts.min(0),pts.max(0)];regions={'front':sample[:,1]<bounds[0][1]+.1,'rear':sample[:,1]>bounds[1][1]-.1,'top':sample[:,2]>bounds[1][2]-1,'bottom':sample[:,2]<bounds[0][2]+1,'left':sample[:,0]<bounds[0][0]+5,'right':sample[:,0]>bounds[1][0]-5}
    distances={}
    for name,mask in regions.items():
        ids=np.flatnonzero(mask);j=ids[np.argmin(ds[ids])]
        distances[name]={'sampled_upper_bound_mm':float(ds[j]),'camera_point_mm':sample[j].tolist(),'shell_point_mm':cp[j].tolist()}
    removal=M.batch_hull([camhull,camhull.translate((0,80,0))])^body
    # Head may occlude the deliberately open face-side boundary when worn.
    h=np.load(R/'Headset_Inputs/Medium_Trial_Registered.npz');head=BVHTree.FromPolygons(h['v'].tolist(),h['f'].tolist(),all_triangles=True)
    def body_block(point,vector):return bool(body.ray_cast(tuple(point),tuple(point+vector*300)))
    def head_block(point,vector):return head.ray_cast(Vector(point),Vector(vector),300)[0] is not None
    exposure=[]
    for name,axis in [('top',(0,0,1)),('bottom',(0,0,-1)),('left',(-1,0,0)),('right',(1,0,0)),
                      ('top_rear_45deg',(0,1,1)),('bottom_rear_45deg',(0,1,-1)),
                      ('left_rear_45deg',(-1,1,0)),('right_rear_45deg',(1,1,0))]:
        direction=np.array(axis,dtype=float);direction/=np.linalg.norm(direction);bare=[];uncovered=[]
        for point in pts:
            if not body_block(point,direction):
                bare.append(point)
                if not head_block(point,direction):uncovered.append(point)
        exposure.append({'view':name,'orthographic_direction':direction.tolist(),'vertices_not_occluded_by_shell':len(bare),'worn_vertices_not_occluded_by_shell_or_head':len(uncovered),'uncovered_examples_mm':[p.tolist() for p in uncovered[:8]]})
    optical=[]
    for ident,name in [(0,'RGB'),(1,'RX'),(2,'TX')]:
        ids=np.unique(cf[pid==ident]);nv=native['v'][ids];keep=abs(nv[:,2]+1)<1e-6
        if name=='TX':keep&=(nv[:,0]>=3.5-1e-6)&(nv[:,0]<=10.5+1e-6)&(abs(nv[:,1])<=2.25+1e-6)
        front=cv[ids[keep]];blocked=[]
        for point in front:
            if body_block(point,np.array([0.,-1.,0.])) or head_block(point,np.array([0.,-1.,0.])):blocked.append(point.tolist())
        center=np.array([{0:-22,1:22,2:7}[ident],0,-1.])@tf[:,:3].T+tf[:,3]
        optical.append({'name':name,'actual_front_vertices_checked':len(front),'blocked_vertices':len(blocked),'measured_center_wearing_mm':center.tolist(),'blocked_examples_mm':blocked[:8]})
    # Every visible camera point in the frontal view must lie inside one of the
    # three specified ports. The decorative long-oval area is not an opening.
    def in_ports(point):
        for o in values['optics']:
            a,b=o['opening_mm'];x=point[0]-o['x'];z=point[2]-o['z']
            if o['name']=='TX':
                # Rounded rectangle R1: rectangular middle plus quarter circles.
                if abs(x)<=a/2 and abs(z)<=b/2 and np.hypot(max(abs(x)-(a/2-1),0),max(abs(z)-(b/2-1),0))<=1+1e-6:return True
            elif (2*x/a)**2+(2*z/b)**2<=1+1e-6:return True
        return False
    visible=0;outside=[]
    for point in pts:
        if not body_block(point,np.array([0.,-1.,0.])) and not head_block(point,np.array([0.,-1.,0.])):
            visible+=1
            if not in_ports(point):outside.append(point.tolist())
    escape=[]
    for direction in [(1,0,0),(-1,0,0),(0,1,0),(0,-1,0),(0,0,1),(0,0,-1)]:
        sweep=M.batch_hull([camhull,camhull.translate(tuple(np.array(direction)*50))]);cross=sweep^closed
        escape.append({'direction':list(direction),'printed_shell_plus_taut_reference_band_crossed_volume_mm3':float(cross.volume())})
    installed_ok=clash.volume()<=TOL
    band_ok=bandclash.volume()<=TOL and threadclash.volume()<=TOL
    removal_ok=removal.volume()<=TOL
    exposure_ok=not outside and all(x['worn_vertices_not_occluded_by_shell_or_head']==0 for x in exposure)
    optics_ok=all(x['actual_front_vertices_checked']>0 and x['blocked_vertices']==0 for x in optical)
    retain_ok=installed_ok and band_ok and all(x['printed_shell_plus_taut_reference_band_crossed_volume_mm3']>TOL for x in escape)
    unchanged=all(digest(R/name)==sha for name,sha in hashes.items())
    band_bounds=[bandq['v'].min(0).tolist(),bandq['v'].max(0).tolist()]
    band_width=float(band_bounds[1][2]-band_bounds[0][2]);opening=values.get('rear_opening_mm')
    gaps=None
    if opening is not None:
        low=opening['center_z']-opening['height']/2;high=opening['center_z']+opening['height']/2
        outer_high=high
        ceiling=values.get('internal_ceiling_mm')
        if ceiling is not None:high=min(high,ceiling['underside_z'])
        lower=max(0.,band_bounds[0][2]-low);upper=max(0.,high-band_bounds[1][2])
        gaps={'outer_opening_z_bounds_mm':[low,outer_high],'effective_camera_corridor_z_bounds_mm':[low,high],
              'effective_top_source':'Actual internal ceiling underside; continuity assessed against the current body mesh.' if ceiling else 'Outer opening',
              'below_band_height_mm':lower,'above_band_height_mm':upper,
              'minimum_caliper_margin_mm':2*radius-max(lower,upper),
              'band_spans_actual_camera_width':bool(band_bounds[0][0]<=bounds[0][0] and band_bounds[1][0]>=bounds[1][0])}
        retain_ok=retain_ok and max(lower,upper)<2*radius and gaps['band_spans_actual_camera_width']
    out={'source_sha256':hashes,'source_changed_during_run':not unchanged,'actual_camera_reference_vertices':len(pts),'actual_camera_reference_triangles':len(cf),'wearing_vs_transformed_native_source_max_error_mm':error,'physical_step_fov_artifacts_present':bool(np.isin(pid,[23,62,63]).any()),
         'fit':{'conservative_camera_hull_body_overlap_mm3':float(clash.volume()),'overlap_components':diagnostic(clash),'hull_to_body_gap_mm':float(camhull.min_gap(body,5)),'sampled_actual_camera_to_body_min_mm':float(ds[k]),'closest_camera_point_mm':sample[k].tolist(),'closest_shell_point_mm':cp[k].tolist(),'regions':distances,'roundoff_overlap_tolerance_mm3':TOL,'pass':installed_ok},
         'removal_with_band_released':{'direction':[0,1,0],'continuous_sweep_length_mm':80,'conservative_sweep_body_overlap_mm3':float(removal.volume()),'overlap_components':diagnostic(removal),'pass':removal_ok},
         'actual_optical_front_visibility':optical,'worn_top_bottom_and_side_exposure':exposure,
         'frontal_only_three_ports':{'visible_camera_vertices':visible,'visible_vertices_outside_three_port_footprints':len(outside),'outside_examples_mm':outside[:8],'pass':not outside},
         'band_route':{'band_body_overlap_mm3':float(threadclash.volume()),'body_overlap_components':diagnostic(threadclash),'band_conservative_camera_overlap_mm3':float(bandclash.volume()),'camera_overlap_components':diagnostic(bandclash),'band_components':len(band.decompose()),'bounds_xyz_mm':band_bounds,'pass':band_ok},
         'retention':{'six_axis_escape_sweeps':escape,'minimum_camera_caliper':caliper,'rear_escape_gaps':gaps,'pass_taut_band_six_axes':retain_ok,'reason':f"The chamber blocks front/top/bottom/left/right travel; a {band_width:g} mm horizontal textile band covers the open rear at Z{band_bounds[0][2]:g}..{band_bounds[1][2]:g} and is threaded and cinched at the side eyes. This assumes a correctly tightened band with the specified folded overlap. Flexible webbing strength, hook-loop closure and hand-flip retention require a real assembly; six translations are not an arbitrary-rotation proof."},
         'limitations':['Camera source is an open STEP shell. A convex hull is only a conservative occupied envelope, not a replacement rectangular camera.','Broad floor/front stop contact is intentional; sub-micrometre tessellation roundoff is reported with an explicit volume tolerance.','Closest-point region distances use actual vertices and facet centroids and are sampled upper bounds.','Occlusion checks use every actual camera mesh vertex in frontal, four principal exterior directions and four rearward 45-degree views; other viewing directions are assessed in rendered inspection.','No operational FOV, USB, cooling, electronics or electrical safety certification is intended for this unpowered prop.'],
         'pass':bool(installed_ok and band_ok and removal_ok and exposure_ok and optics_ok and retain_ok and unchanged),'runtime_seconds':time.time()-start}
    (P/'checks/camera_fit.json').write_text(json.dumps(out,indent=2),encoding='utf8')
    print(json.dumps({k:out[k] for k in ['pass','source_changed_during_run','fit','removal_with_band_released','actual_optical_front_visibility','worn_top_bottom_and_side_exposure','frontal_only_three_ports','band_route','runtime_seconds']},indent=2))
if __name__=='__main__':main()
