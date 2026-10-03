"""Self-contained head/slot audit for the current open-back prop front.

Nominal skin contact is allowed. No clearance margin is added to the geometry.
Run --phase distances with NumPy/SciPy, then --phase classify and --phase slots
with CAD Python that has VTK/manifold3d. Head and slot data are local inputs.
"""
from pathlib import Path
import argparse,hashlib,json
import numpy as np
from mesh_distance import continuous_min

P=Path(__file__).resolve().parent
ART=P.parent
ROOT=ART.parent
G=ART/'geometry'
INPUTS=ROOT/'Headset_Inputs'
HEAD=INPUTS/'Medium_Trial_Registered.npz'
OUTPUT=P/'head_fit.json'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def load(path):
    a=np.load(path);return a['v'],a['f']
def parts():
    values=json.loads((G/'geometry_values.json').read_text(encoding='utf8'))
    names=values.get('head_audit_parts')
    if not names:raise ValueError('geometry_values.json needs head_audit_parts for actual material/reference parts')
    assert 'front_body' in names and 'camera' in names
    assert len(names)==len(set(names))
    return names
def assert_fresh(report):
    assert report['head_sha256']==sha(HEAD),'Head source changed during audit'
    assert report['build_source_sha256']==sha(ART/'build.py'),'Build source changed during audit'
    assert report['geometry_values_sha256']==sha(G/'geometry_values.json'),'Geometry metadata changed during audit'
    assert report['head_audit_parts']==parts(),'Audited part manifest changed'
    for name,expected in report['source_geometry_sha256'].items():
        assert expected==sha(G/(name+'.npz')),name+' source changed during audit'
    if 'audit_source_sha256' in report:
        for name,expected in report['audit_source_sha256'].items():
            assert expected==sha(P/name),'Audit method changed during audit: '+name

def closed_ray_parity(v,f,points):
    """Deterministic exact triangle rays for a watertight material mesh.

    VTK supplies a conservative cell broadphase; NumPy evaluates the actual
    triangle intersections. Shared-edge hits are counted once. This avoids
    vtkSelectEnclosedPoints' scale-relative default ray tolerance.
    """
    import vtk
    from vtk.util.numpy_support import numpy_to_vtk,numpy_to_vtkIdTypeArray
    vertex=vtk.vtkPoints();vertex.SetData(numpy_to_vtk(np.ascontiguousarray(v,dtype=np.float64),deep=True))
    cells=vtk.vtkCellArray();cells.SetData(numpy_to_vtkIdTypeArray(np.arange(0,len(f)*3+1,3,dtype=np.int64),deep=True),numpy_to_vtkIdTypeArray(np.ascontiguousarray(f.ravel(),dtype=np.int64),deep=True))
    surface=vtk.vtkPolyData();surface.SetPoints(vertex);surface.SetPolys(cells)
    assert vtk.vtkSelectEnclosedPoints.IsSurfaceClosed(surface),'Material mesh is not watertight'
    locator=vtk.vtkStaticCellLocator();locator.SetDataSet(surface);locator.BuildLocator()
    tri=v[f];lo=tri.min((0,1));hi=tri.max((0,1))
    direction=np.array([1.,.3791267381,.1726589193]);direction/=np.linalg.norm(direction)
    length=float(np.linalg.norm(hi-lo)*2+2);ids=vtk.vtkIdList();inside=np.zeros(len(points),dtype=bool)
    for index,point in enumerate(points):
        if np.any(point<lo-1e-9) or np.any(point>hi+1e-9):continue
        ids.Reset();locator.FindCellsAlongLine(point,point+direction*length,0.,ids)
        if not ids.GetNumberOfIds():continue
        t=tri[np.fromiter((ids.GetId(i) for i in range(ids.GetNumberOfIds())),dtype=np.int64)]
        edge1=t[:,1]-t[:,0];edge2=t[:,2]-t[:,0];cross1=np.cross(direction,edge2)
        determinant=np.einsum('ij,ij->i',edge1,cross1)
        keep=np.abs(determinant)>1e-15
        t=t[keep];edge1=edge1[keep];edge2=edge2[keep];cross1=cross1[keep];determinant=determinant[keep]
        relative=point-t[:,0];cross2=np.cross(relative,edge1)
        u=np.einsum('ij,ij->i',relative,cross1)/determinant
        w=np.einsum('ij,j->i',cross2,direction)/determinant
        distance=np.einsum('ij,ij->i',edge2,cross2)/determinant
        hits=np.sort(distance[(u>=-1e-10)&(w>=-1e-10)&(u+w<=1+1e-10)&(distance>1e-8)&(distance<=length)])
        count=int(len(hits)>0)+int((np.diff(hits)>1e-7).sum())
        inside[index]=bool(count%2)
    return inside

def distances():
    from scipy.spatial import cKDTree
    HV,HF=load(HEAD);HT=HV[HF];names=parts()
    hrefs=np.unique(HF.ravel());tree=cKDTree(HV[hrefs])
    previous=json.loads(OUTPUT.read_text(encoding='utf8')) if OUTPUT.exists() else {}
    report={'head_source':str(HEAD.relative_to(ROOT)),'head_sha256':sha(HEAD),'head_pose_unchanged':True,
            'build_source_sha256':sha(ART/'build.py'),'geometry_values_sha256':sha(G/'geometry_values.json'),
            'audit_source_sha256':{n:sha(P/n) for n in ['head_fit.py','mesh_distance.py']},
            'head_audit_parts':names,'source_geometry_sha256':{n:sha(G/(n+'.npz')) for n in names},
            'skin_contact_allowed':True,'intentional_skin_clearance_added_mm':0,
            'basis':'Actual unchanged registered triangular head; all current material parts and actual camera checked. Contact is allowed and does not by itself fail fit. No old BTTF collision exception or earlier clearance threshold is imposed.',
            'parts':{}}
    if (previous.get('head_sha256')==report['head_sha256'] and
        previous.get('source_geometry_sha256',{}).get('camera')==report['source_geometry_sha256']['camera'] and
        'camera_first_skin_contact' in previous):
        report['camera_first_skin_contact']=previous['camera_first_skin_contact']
        report['camera_first_skin_contact']['reused_for_identical_head_and_camera_hashes']=True
    for name in names:
        V,F=load(G/(name+'.npz'));refs=np.unique(F.ravel())
        upper=float(tree.query(V[refs])[0].min());pad=upper+1e-7
        lo=V[refs].min(0)-pad;hi=V[refs].max(0)+pad
        keep=np.all(HT.max(1)>=lo,axis=1)&np.all(HT.min(1)<=hi,axis=1)
        selected=HT[keep];localV=selected.reshape(-1,3);localF=np.arange(len(localV)).reshape(-1,3)
        result=continuous_min(localV,localF,V,F)
        if result['head_face_index']>=0:result['head_face_index']=int(np.flatnonzero(keep)[result['head_face_index']])
        result['excluded_head_triangle_distance_lower_bound_mm']=pad
        result['head_triangles_checked']=len(selected)
        report['parts'][name]={'continuous_triangle_clearance':result}
        print(name,'continuous distance',result['distance_mm'],flush=True)
    assert_fresh(report)
    OUTPUT.write_text(json.dumps(report,indent=2),encoding='utf8')

def classify(epsilon):
    import vtk
    from vtk.util.numpy_support import numpy_to_vtk,numpy_to_vtkIdTypeArray
    def poly(v,f):
        points=vtk.vtkPoints();points.SetData(numpy_to_vtk(np.ascontiguousarray(v,dtype=np.float64),deep=True))
        ca=vtk.vtkCellArray();ca.SetData(numpy_to_vtkIdTypeArray(np.arange(0,len(f)*3+1,3,dtype=np.int64),deep=True),numpy_to_vtkIdTypeArray(np.ascontiguousarray(f.ravel(),dtype=np.int64),deep=True))
        data=vtk.vtkPolyData();data.SetPoints(points);data.SetPolys(ca);return data
    def field(data):
        result=vtk.vtkImplicitPolyDataDistance();result.SetInput(data);return result
    def signed_record(implicit,points,closed_surface=None):
        ds=np.array([implicit.EvaluateFunction(p) for p in points])
        # The closest-face normal can give the wrong sign at a concave edge.
        # For a closed material surface, ray parity supplies the inside sign;
        # the distance magnitude still comes from the closest triangle.
        corrected=0
        if closed_surface is not None:
            assert vtk.vtkSelectEnclosedPoints.IsSurfaceClosed(closed_surface)
            from vtk.util.numpy_support import vtk_to_numpy
            sv=vtk_to_numpy(closed_surface.GetPoints().GetData())
            sf=vtk_to_numpy(closed_surface.GetPolys().GetConnectivityArray()).reshape(-1,3)
            inside=closed_ray_parity(sv,sf,points)
            corrected=int(((ds<0)!=inside).sum());ds=np.where(inside,-np.abs(ds),np.abs(ds))
        ix=int(ds.argmin())
        return {'points_checked':len(points),'closest_normal_signs_corrected_by_closed_surface_parity':corrected,
                'points_strictly_inside':int((ds<-1e-6).sum()),
                'points_deeper_than_contact_epsilon':int((ds<-epsilon).sum()),
                'minimum_signed_sample_distance_mm':float(ds[ix]),
                'maximum_sampled_penetration_mm':max(0.,float(-ds[ix])),
                'minimum_witness_xyz_mm':points[ix].tolist()}
    report=json.loads(OUTPUT.read_text(encoding='utf8'));assert_fresh(report)
    HV,HF=load(HEAD);HT=HV[HF];implicit=field(poly(HV,HF))
    controls={'interior_center':[0,105,45],'anterior_exterior':[0,-50,45],'lateral_exterior':[100,125,35]}
    signs={n:float(implicit.EvaluateFunction(v)) for n,v in controls.items()}
    assert signs['interior_center']<0 and signs['anterior_exterior']>0 and signs['lateral_exterior']>0,signs
    report['classification_controls_mm']=signs
    report['classification_contact_epsilon_mm']=epsilon
    report['classification_contact_epsilon_note']='Numerical reporting tolerance for nominal contact, not a design gap. Exact sampled penetration depths and witnesses are retained; this is not a physical fit certification.'
    for name in report['head_audit_parts']:
        V,F=load(G/(name+'.npz'));refs=np.unique(F.ravel())
        pts=[V[refs],V[F].mean(1)]
        if name!='camera':
            edges=np.unique(np.sort(np.concatenate([F[:,[0,1]],F[:,[1,2]],F[:,[2,0]]]),axis=1),axis=0)
            pts.append(V[edges].mean(1))
        candidate=signed_record(implicit,np.vstack(pts))
        # Reverse samples catch a skin vertex entering a broad candidate face
        # even when the candidate vertices and centroid remain outside.
        lo=V[refs].min(0)-epsilon;hi=V[refs].max(0)+epsilon
        keep=np.all(HT.max(1)>=lo,axis=1)&np.all(HT.min(1)<=hi,axis=1)
        selected=HT[keep]
        hp=np.vstack([HV[np.unique(HF[keep].ravel())],selected.mean(1)]) if len(selected) else np.empty((0,3))
        if name=='camera':
            # STEP assembly surfaces retain individual face seams and inward
            # normals. They are valid for exact surface distance/collision but
            # their closest-normal sign is not a valid volume containment test.
            reverse={'points_checked':0,'points_strictly_inside':0,'points_deeper_than_contact_epsilon':0,
                     'minimum_signed_sample_distance_mm':None,'maximum_sampled_penetration_mm':0.,
                     'minimum_witness_xyz_mm':None,
                     'method':'Not classified against open STEP face seams. Actual surface collision bisection below establishes first skin contact.'}
        else:
            part_surface=poly(V,F)
            reverse=signed_record(field(part_surface),hp,part_surface) if len(hp) else {'points_checked':0,'points_strictly_inside':0,'points_deeper_than_contact_epsilon':0,'minimum_signed_sample_distance_mm':None,'maximum_sampled_penetration_mm':0.,'minimum_witness_xyz_mm':None}
        report['parts'][name]['part_points_against_skin']=candidate
        report['parts'][name]['skin_points_against_part']=reverse
        report['parts'][name]['penetration_within_contact_epsilon']=candidate['points_deeper_than_contact_epsilon']==0 and reverse['points_deeper_than_contact_epsilon']==0
        print(name,'sampled penetration mm',candidate['maximum_sampled_penetration_mm'],reverse['maximum_sampled_penetration_mm'],
              'part witness',candidate['minimum_witness_xyz_mm'],'skin witness',reverse['minimum_witness_xyz_mm'],flush=True)
    if 'camera_first_skin_contact' not in report:
        V,F=load(G/'camera.npz')
        camera_refs=V[np.unique(F.ravel())];lo=camera_refs.min(0)-[0,.500001,0];hi=camera_refs.max(0)+[0,.500001,0]
        selected=np.all(HT.max(1)>=lo,axis=1)&np.all(HT.min(1)<=hi,axis=1)
        collision=vtk.vtkCollisionDetectionFilter();collision.SetInputData(0,poly(HV,HF[selected]));collision.SetInputData(1,poly(V,F))
        stationary=vtk.vtkMatrix4x4();stationary.Identity();moving=vtk.vtkMatrix4x4();moving.Identity()
        collision.SetMatrix(0,stationary);collision.SetMatrix(1,moving);collision.SetCollisionModeToFirstContact()
        collision.SetBoxTolerance(0);collision.SetCellTolerance(0);collision.SetNumberOfCellsPerNode(2)
        def camera_hits(dy):
            moving.SetElement(1,3,dy);collision.Update();return bool(collision.GetNumberOfContacts())
        low=-.5;high=.5
        assert not camera_hits(low) and camera_hits(high),'Camera contact is not within 0.5 mm of nominal pose'
        for unused in range(20):
            middle=(low+high)/2
            if camera_hits(middle):high=middle
            else:low=middle
        posterior=max(0.,-low)
        report['camera_first_skin_contact']={'method':'Exact VTK triangle surface collision, bisection along wearing +Y at unchanged level optical height.',
                 'additional_y_before_contact_mm':low,'additional_y_at_contact_mm':high,
                 'bisection_resolution_mm':high-low,'pose_posterior_of_first_contact_upper_bound_mm':posterior,
                 'nominal_contact_within_epsilon':posterior<=epsilon}
    else:
        posterior=report['camera_first_skin_contact']['pose_posterior_of_first_contact_upper_bound_mm']
        report['camera_first_skin_contact']['nominal_contact_within_epsilon']=posterior<=epsilon
    report['camera_first_skin_contact']['source_head_sha256']=report['head_sha256']
    report['camera_first_skin_contact']['source_camera_sha256']=report['source_geometry_sha256']['camera']
    report['parts']['camera']['penetration_within_contact_epsilon'] &= posterior<=epsilon
    report['all_parts_sampled_penetration_within_contact_epsilon']=all(p['penetration_within_contact_epsilon'] for p in report['parts'].values())
    report['classification_limit']='Every referenced vertex and face centroid is classified against the head; material edge midpoints are additionally checked. Reverse material classification uses watertight ray parity to correct concave closest-normal sign artifacts. Camera STEP normals do not supply a valid containment sign, so exact triangle collision bisection verifies its nominal first skin contact. Negative sample depths are not an exact continuous maximum penetration.'
    assert_fresh(report);OUTPUT.write_text(json.dumps(report,indent=2),encoding='utf8')

def slots():
    import manifold3d as md
    report=json.loads(OUTPUT.read_text(encoding='utf8'));assert_fresh(report)
    datums=json.loads((INPUTS/'datums.json').read_text(encoding='utf8'))
    V,F=load(G/'front_body.npz')
    body=md.Manifold(md.Mesh64(vert_properties=np.ascontiguousarray(V,dtype=np.float64),tri_verts=np.ascontiguousarray(F,dtype=np.uint64)))
    assert body.status()==md.Error.NoError
    transverse=body.transform([[0,1,0,0],[0,0,1,0],[1,0,0,0]])
    ylo,yhi=datums['terminal_slot_y'];zlo,zhi=datums['terminal_slot_z']
    expected=np.array([[ylo,zlo],[yhi,zhi]])
    records={};tri=V[F];normal=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
    for side in ['left','right']:
        xrange=datums['terminal_'+side+'_x'];xcenter=float(np.mean(xrange))
        polys=transverse.slice(xcenter).to_polygons()
        bounds=[np.array([p.min(0),p.max(0)]) for p in polys]
        matches=[p for p,b in zip(polys,bounds) if np.max(np.abs(b-expected))<1e-6]
        near=(np.abs(tri[:,:,0].mean(1)-xcenter)<8)
        front=(np.abs(tri[:,:,1]-ylo).max(1)<1e-6)&(tri[:,:,2].min(1)>=zlo-1e-6)&(tri[:,:,2].max(1)<=zhi+1e-6)&(normal[:,1]>1e-12)
        rear=(np.abs(tri[:,:,1]-yhi).max(1)<1e-6)&(tri[:,:,2].min(1)>=zlo-1e-6)&(tri[:,:,2].max(1)<=zhi+1e-6)&(normal[:,1]<-1e-12)
        walls=tri[near&(front|rear)]
        actual_x=[float(walls[:,:,0].min()),float(walls[:,:,0].max())] if len(walls) else None
        center_error=abs(float(np.mean(actual_x))-xcenter) if actual_x else None
        records[side]={'expected_slot_x_center_mm':xcenter,'expected_slot_yz_bounds_mm':expected.tolist(),
                       'matching_hole_loops':len(matches),'actual_slot_wall_x_extent_mm':actual_x,
                       'slot_lateral_center_error_mm':center_error,
                       'preserved':len(matches)>0 and center_error is not None and center_error<1e-6}
    reach=float(V[:,1].max());expected_reach=float(datums['terminal_reach_y'])
    report['terminal_slots']={'datums_source':'Headset_Inputs/datums.json','datums_sha256':sha(INPUTS/'datums.json'),
                              'sides':records,'expected_terminal_reach_y_mm':expected_reach,'actual_terminal_reach_y_mm':reach,
                              'reach_unchanged':abs(reach-expected_reach)<1e-6,
                              'all_slot_locations_and_reach_preserved':all(r['preserved'] for r in records.values()) and abs(reach-expected_reach)<1e-6}
    assert_fresh(report);OUTPUT.write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report['terminal_slots'],indent=2))

def measurements():
    import zipfile,xml.etree.ElementTree as ET
    report=json.loads(OUTPUT.read_text(encoding='utf8'));assert_fresh(report)
    values=json.loads((G/'geometry_values.json').read_text(encoding='utf8'))
    HV,HF=load(HEAD);referenced_head=HV[np.unique(HF.ravel())]
    tip=referenced_head[referenced_head[:,1].argmin()]
    records={}
    for name in report['head_audit_parts']:
        V,F=load(G/(name+'.npz'));referenced=V[np.unique(F.ravel())];lo=referenced.min(0);hi=referenced.max(0)
        tri=V[F]
        records[name]={'referenced_bounds_xyz_mm':[lo.tolist(),hi.tolist()],
                       'referenced_size_xyz_mm':(hi-lo).tolist(),
                       'signed_mesh_volume_cm3':float(np.einsum('ij,ij->i',tri[:,0],np.cross(tri[:,1],tri[:,2])).sum()/6000),
                       'front_ahead_of_nose_tip_y_mm':float(tip[1]-lo[1])}
    source=INPUTS/'BTTF_Glasses.3mf';ns={'c':'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'}
    with zipfile.ZipFile(source) as archive:
        model=ET.fromstring(archive.read('3D/3dmodel.model'))
        item=model.find('c:build/c:item[@objectid="2"]',ns)
        item_t=np.array(list(map(float,item.get('transform').split()))).reshape(4,3)
        component=model.find('c:resources/c:object[@id="2"]/c:components/c:component',ns)
        component_t=np.array(list(map(float,component.get('transform').split()))).reshape(4,3)
        path=component.get('{http://schemas.microsoft.com/3dmanufacturing/production/2015/06}path').lstrip('/')
        geometry=ET.fromstring(archive.read(path)).find('c:resources/c:object[@id="'+component.get('objectid')+'"]/c:mesh',ns)
        V=np.array([[float(point.get(k)) for k in ['x','y','z']] for point in geometry.find('c:vertices',ns)])
        F=np.array([[int(face.get(k)) for k in ['v1','v2','v3']] for face in geometry.find('c:triangles',ns)])
        tri=V[F];raw=np.einsum('ij,ij->i',tri[:,0],np.cross(tri[:,1],tri[:,2])).sum()/6000
        normal_volume=float(abs(raw*np.linalg.det(component_t[:3])*np.linalg.det(item_t[:3])))
    camera_native=ART/'inputs/camera_physical_native.npz';NV,NF=load(camera_native);CV,CF=load(G/'camera.npz')
    transform=np.array(values['camera_transform_native_to_wearing'])
    assert np.array_equal(NF,CF),'Camera source faces changed'
    assert NV.shape==CV.shape
    residual=float(np.abs(NV@transform[:,:3].T+transform[:,3]-CV).max())
    assert residual<1e-9,'Camera mesh differs from declared true-camera pose'
    body_volume=abs(records['front_body']['signed_mesh_volume_cm3'])
    BV,BF=load(G/'front_body.npz');BT=BV[BF];front_portions=[]
    for y in [-21.4,0,20,43]:
        chunks=[BT[BT[:,:,1]<=y]]
        for first,second in [(0,1),(1,2),(2,0)]:
            keep=(BT[:,first,1]<=y)!=(BT[:,second,1]<=y)
            a=BT[keep,first];b=BT[keep,second]
            ratio=(y-a[:,1])/(b[:,1]-a[:,1])
            chunks.append(a+ratio[:,None]*(b-a))
        points=np.vstack(chunks);lo=points.min(0);hi=points.max(0)
        front_portions.append({'cut_y_le_mm':y,'bounds_xyz_mm':[lo.tolist(),hi.tolist()],'size_xyz_mm':(hi-lo).tolist()})
    central_chunks=[BT[np.abs(BT[:,:,0])<1e-9]]
    for first,second in [(0,1),(1,2),(2,0)]:
        keep=(BT[:,first,0]<=0)!=(BT[:,second,0]<=0)
        a=BT[keep,first];b=BT[keep,second];ratio=-a[:,0]/(b[:,0]-a[:,0])
        central_chunks.append(a+ratio[:,None]*(b-a))
    central_points=np.vstack(central_chunks);central_lo=central_points.min(0);central_hi=central_points.max(0)
    report['measurements']={'head_anterior_nose_tip_xyz_mm':tip.tolist(),
        'nose_projection_note':'Anterior Y projection only; this does not compare points at the same height.',
        'parts':records,'camera_actual_transform_max_residual_mm':residual,
        'camera_native_source_sha256':sha(camera_native),'camera_transform_native_to_wearing':transform.tolist(),
        'optical_axis_in_wearing_xyz':(transform[:,:3]@np.array([0,0,1.])).tolist(),
        'bttf_normal_source':'Headset_Inputs/BTTF_Glasses.3mf build object 2',
        'bttf_normal_source_sha256':sha(source),'bttf_normal_material_volume_cm3':normal_volume,
        'body_volume_ratio_to_normal':body_volume/normal_volume,
        'body_volume_difference_to_normal_cm3':body_volume-normal_volume,
        'actual_front_portions':front_portions,
        'front_center_x0_cross_section_bounds_yz_mm':[central_lo[1:].tolist(),central_hi[1:].tolist()],
        'front_center_x0_height_mm':float(central_hi[2]-central_lo[2]),
        'printed_body_plus_reference_band_cm3':body_volume+abs(records['retention_band']['signed_mesh_volume_cm3'])}
    assert_fresh(report);OUTPUT.write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report['measurements'],indent=2))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--phase',choices=['distances','classify','slots','measurements'],required=True)
    parser.add_argument('--contact-epsilon-mm',type=float,default=.05)
    args=parser.parse_args()
    if args.phase=='distances':distances()
    elif args.phase=='classify':classify(args.contact_epsilon_mm)
    elif args.phase=='slots':slots()
    else:measurements()
if __name__=='__main__':main()
