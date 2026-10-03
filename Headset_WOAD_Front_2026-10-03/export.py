"""Export the wearing assembly and a single black body already posed to print."""
from pathlib import Path
import hashlib,json,zipfile
import xml.etree.ElementTree as ET
import numpy as np
import manifold3d as md
P=Path(__file__).resolve().parent;G=P/'geometry';R=P.parent
NS='http://schemas.microsoft.com/3dmanufacturing/core/2015/02';ET.register_namespace('',NS)
def tag(s):return '{'+NS+'}'+s
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def compact(q):
    v=np.asarray(q['v']);f=np.asarray(q['f'])
    assert v.ndim==2 and v.shape[1]==3 and f.ndim==2 and f.shape[1]==3
    assert np.isfinite(v).all() and np.issubdtype(f.dtype,np.integer)
    assert f.min()>=0 and f.max()<len(v)
    used=np.unique(f);return v[used],np.searchsorted(used,f),used

def write_archive(path,model):
    members={'[Content_Types].xml':b'<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>','_rels/.rels':b'<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>','3D/3dmodel.model':ET.tostring(model,encoding='UTF-8',xml_declaration=True)}
    with zipfile.ZipFile(path,'w') as ar:
        for name,data in members.items():
            info=zipfile.ZipInfo(name,(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;ar.writestr(info,data,compresslevel=6)
    with zipfile.ZipFile(path) as ar:return ET.fromstring(ar.read('3D/3dmodel.model'))

def bed_contact(v,f,tolerance=1e-7):
    """Exact planar surface triangles and their edge-connected patches."""
    mask=np.max(abs(v[f][:,:,2]),axis=1)<=tolerance
    cf=f[mask];tri=v[cf]
    cross=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);area=np.linalg.norm(cross,axis=1)/2
    assert len(cf)>0 and np.all(cross[:,2]<1e-10),'No genuine downward bed surface'
    parent=np.arange(len(cf));owners=np.tile(np.arange(len(cf)),3)
    edges=np.sort(np.concatenate([cf[:,[0,1]],cf[:,[1,2]],cf[:,[2,0]]]),axis=1)
    order=np.lexsort((edges[:,1],edges[:,0]));edges=edges[order];owners=owners[order]
    pairs=np.flatnonzero(np.all(edges[1:]==edges[:-1],axis=1))
    def root(a):
        while parent[a]!=a:parent[a]=parent[parent[a]];a=parent[a]
        return a
    for j in pairs:
        a,b=root(owners[j]),root(owners[j+1])
        if a!=b:parent[b]=a
    labels=np.array([root(i) for i in range(len(cf))]);patches=[]
    for label in np.unique(labels):
        ids=np.flatnonzero(labels==label);points=v[np.unique(cf[ids])]
        patches.append({'area_mm2':float(area[ids].sum()),'triangles':len(ids),
                        'bounds_xyz_mm':[points.min(0).tolist(),points.max(0).tolist()]})
    patches.sort(key=lambda p:p['area_mm2'],reverse=True)
    return {'plane_z_mm':0,'triangle_z_tolerance_mm':tolerance,'total_area_mm2':float(area.sum()),
            'triangles':len(cf),'edge_connected_patches':len(patches),'patches':patches,
            'method':'Unmodified mesh triangles coplanar with the bed; connectivity only through shared full mesh edges.'}

def print_ready(v,f,source_volume,values):
    angle=values['print_bearing_plane']['rotation_about_wearing_x_deg'];radians=np.deg2rad(angle)
    rotation=np.array([[1.,0,0],[0,np.cos(radians),-np.sin(radians)],[0,np.sin(radians),np.cos(radians)]])
    posed=v@rotation.T;translation=np.zeros(3)
    translation[:2]=128-(posed[:,:2].min(0)+posed[:,:2].max(0))/2
    translation[2]=-posed[:,2].min();posed+=translation
    bounds=[posed.min(0),posed.max(0)]
    beds={}
    for name,bed in [('256x256',[256,256]),('H2C_330x320',[330,320])]:
        bed=np.array(bed);margin=15.
        fits=bool(np.all(bounds[0][:2]-margin>=-1e-9) and np.all(bounds[1][:2]+margin<=bed+1e-9))
        beds[name]={'bed_xy_mm':bed.tolist(),'support_envelope_allowance_mm':10,'brim_allowance_mm':5,
                    'combined_envelope_allowance_mm':margin,'fits_body_support_envelope_and_brim':fits,
                    'body_to_bed_edge_margins_minxy_maxxy_mm':[bounds[0][:2].tolist(),(bed-bounds[1][:2]).tolist()]}
        assert fits
    assert abs(bounds[0][2])<1e-10
    m=md.Manifold(md.Mesh64(vert_properties=np.ascontiguousarray(posed,dtype=np.float64),tri_verts=np.ascontiguousarray(f,dtype=np.uint64)))
    assert m.status()==md.Error.NoError and len(m.decompose())==1 and m.volume()>0
    volume=float(m.volume());assert abs(volume-source_volume)<1e-7
    model=ET.Element(tag('model'),unit='millimeter')
    ET.SubElement(model,tag('metadata'),name='Title').text='WOAD-inspired front - one black body ready to print'
    ET.SubElement(model,tag('metadata'),name='Description').text='One printable black shell, no reference objects and no blue material assignment. The integral groove remains in the geometry for painting after printing. Rotation and bed placement are baked into full-precision vertices.'
    resources=ET.SubElement(model,tag('resources'));materials=ET.SubElement(resources,tag('basematerials'),id='1')
    ET.SubElement(materials,tag('base'),name='Body_black',displaycolor='#23262BFF')
    obj=ET.SubElement(resources,tag('object'),id='2',type='model',name='PRINT_Front_shell_black',pid='1',pindex='0')
    me=ET.SubElement(obj,tag('mesh'));vs=ET.SubElement(me,tag('vertices'));ts=ET.SubElement(me,tag('triangles'))
    for point in posed:ET.SubElement(vs,tag('vertex'),x=format(point[0],'.17g'),y=format(point[1],'.17g'),z=format(point[2],'.17g'))
    for face in f:ET.SubElement(ts,tag('triangle'),v1=str(face[0]),v2=str(face[1]),v3=str(face[2]))
    build=ET.SubElement(model,tag('build'));ET.SubElement(build,tag('item'),objectid='2')
    path=P/'Front_Print_Ready.3mf';back=write_archive(path,model)
    objects=back.findall(tag('resources')+'/'+tag('object'));items=back.findall(tag('build')+'/'+tag('item'))
    bases=back.findall(tag('resources')+'/'+tag('basematerials')+'/'+tag('base'))
    assert len(objects)==len(items)==len(bases)==1 and objects[0].get('type')=='model'
    assert bases[0].get('name')=='Body_black' and objects[0].get('pid')=='1' and objects[0].get('pindex')=='0'
    assert 'transform' not in items[0].attrib
    rv=np.array([[float(pt.get(k)) for k in 'xyz'] for pt in objects[0].findall('.//'+tag('vertex'))])
    tris=objects[0].findall('.//'+tag('triangle'));rf=np.array([[int(pt.get(k)) for k in ['v1','v2','v3']] for pt in tris])
    assert np.array_equal(rv,posed) and np.array_equal(rf,f) and np.unique(rf).size==len(rv)
    assert all(not any(k in t.attrib for k in ['pid','p1','p2','p3']) for t in tris)
    return {'file':path.name,'sha256':digest(path),'printable_objects':1,'reference_objects':0,
            'base_materials':1,'only_black_material':True,'blue_face_assignments':0,
            'wearing_to_print_rotation_about_x_deg':float(angle),'rotation_matrix':rotation.tolist(),
            'translation_mm':translation.tolist(),'placement_center_xy_mm':[128,128],
            'used_vertex_bounds_xyz_mm':[p.tolist() for p in bounds],
            'triangle_indices_unchanged':True,'vertices':len(posed),'triangles':len(f),
            'volume_cm3':volume/1000,'source_volume_delta_mm3':volume-source_volume,
            'closed_connected_manifold':True,'coordinates_and_indices_readback_exact':True,
            'physical_groove_preserved':True,'bed_fit':beds,'bed_contact':bed_contact(posed,f),'pass':True}

def main():
    paths=[('PRINT_Front_shell',G/'front_body.npz',True,0),
           ('REFERENCE_Head_do_not_print',R/'Headset_Inputs/Medium_Trial_Registered.npz',False,2),
           ('REFERENCE_Actual_CS30_customer_STEP_do_not_print',G/'camera.npz',False,3),
           ('REFERENCE_Textile_cinch_band_do_not_print',G/'retention_band.npz',False,4)]
    sources=[p for _,p,_,_ in paths]+[G/'geometry_values.json',R/'Headset_Inputs/CS30_customer.stp',R/'Headset_Inputs/BTTF_Glasses.3mf',R/'Headset_Rear/Rear_Wearing.3mf']
    hashes={str(p.relative_to(R)).replace('\\','/'):digest(p) for p in sources}
    model=ET.Element(tag('model'),unit='millimeter')
    ET.SubElement(model,tag('metadata'),name='Title').text='WOAD-inspired prop front - wearing assembly'
    ET.SubElement(model,tag('metadata'),name='Description').text='One connected printable body with black and blue face colors. Camera is unpowered; head, actual camera and textile cinch band are nonprintable REFERENCE objects. Wearing coordinates preserved.'
    resources=ET.SubElement(model,tag('resources'));materials=ET.SubElement(resources,tag('basematerials'),id='1');build=ET.SubElement(model,tag('build'))
    for name,color in [('Body_black','#23262BFF'),('Body_blue','#3B80B8FF'),('Reference_head','#BEC6C9FF'),('Reference_camera','#D6A759FF'),('Reference_textile_band','#34383DFF')]:ET.SubElement(materials,tag('base'),name=name,displaycolor=color)
    rows=[];exported=[]
    for i,(name,path,printable,index) in enumerate(paths,2):
        q=np.load(path);v,f,used=compact(q);material=None
        if printable:
            key='material' if 'material' in q.files else 'part';assert key in q.files,'Missing body face material IDs'
            material=np.asarray(q[key]);assert material.shape==(len(f),) and np.isin(material,[0,1]).all()
        obj=ET.SubElement(resources,tag('object'),id=str(i),type='model' if printable else 'other',name=name,pid='1',pindex=str(index))
        me=ET.SubElement(obj,tag('mesh'));vs=ET.SubElement(me,tag('vertices'));ts=ET.SubElement(me,tag('triangles'))
        for point in v:ET.SubElement(vs,tag('vertex'),x=format(point[0],'.17g'),y=format(point[1],'.17g'),z=format(point[2],'.17g'))
        for j,face in enumerate(f):
            attrs={'v1':str(face[0]),'v2':str(face[1]),'v3':str(face[2])}
            if printable:attrs.update(pid='1',p1=str(material[j]),p2=str(material[j]),p3=str(material[j]))
            ET.SubElement(ts,tag('triangle'),**attrs)
        ET.SubElement(build,tag('item'),objectid=str(i))
        row={'name':name,'printable':printable,'source':str(path.relative_to(R)).replace('\\','/'),'source_sha256':digest(path),'vertices':len(v),'triangles':len(f),'source_unused_vertices_removed':len(q['v'])-len(used),'used_vertex_bounds_xyz_mm':[v.min(0).tolist(),v.max(0).tolist()],'triangle_index_min_max':[int(f.min()),int(f.max())]}
        if printable:
            m=md.Manifold(md.Mesh64(vert_properties=np.ascontiguousarray(v,dtype=np.float64),tri_verts=np.ascontiguousarray(f,dtype=np.uint64)))
            assert m.status()==md.Error.NoError and len(m.decompose())==1 and m.volume()>0
            edges=np.sort(np.concatenate([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]]),axis=1);_,count=np.unique(edges,axis=0,return_counts=True);assert (count==2).all()
            row.update(volume_cm3=float(m.volume())/1000,closed_connected_manifold=True,material_triangle_counts={str(k):int(np.sum(material==k)) for k in [0,1]})
        rows.append(row);exported.append((v,f,material))
    out=P/'Front_Wearing.3mf'
    back=write_archive(out,model)
    objects=back.findall(tag('resources')+'/'+tag('object'));items=back.findall(tag('build')+'/'+tag('item'))
    assert len(objects)==len(items)==4 and sum(ob.get('type')=='model' for ob in objects)==1
    assert all('transform' not in it.attrib for it in items)
    for ob,(v,f,material),row in zip(objects,exported,rows):
        rv=np.array([[float(pt.get(k)) for k in 'xyz'] for pt in ob.findall('.//'+tag('vertex'))]);tris=ob.findall('.//'+tag('triangle'));rf=np.array([[int(pt.get(k)) for k in ['v1','v2','v3']] for pt in tris])
        assert np.array_equal(rv,v) and np.array_equal(rf,f) and np.unique(rf).size==len(rv)
        if material is not None:assert all(pt.get('pid')=='1' and int(pt.get('p1'))==int(pt.get('p2'))==int(pt.get('p3'))==int(k) for pt,k in zip(tris,material))
        row['readback_coordinates_and_indices_exact']=True
    ready=print_ready(exported[0][0],exported[0][1],rows[0]['volume_cm3']*1000,
                      json.loads((G/'geometry_values.json').read_text(encoding='utf8')))
    assert all(digest(R/name)==sha for name,sha in hashes.items()),'Inputs changed during export'
    rear_check=json.loads((R/'Headset_Rear/checks/export.json').read_text(encoding='utf8'));rear_hash=digest(R/'Headset_Rear/Rear_Wearing.3mf');assert rear_check['rear_body_arrays_unchanged'] and rear_hash==rear_check['sha256']
    result={'file':out.name,'sha256':digest(out),'wearing_coordinates_preserved_exactly':True,'single_printable_body':True,'objects':rows,'print_ready':ready,'source_sha256':hashes,'source_changed_during_run':False,'rear_3mf_sha256':rear_hash,'rear_body_arrays_unchanged':True,'pass':True}
    (P/'checks').mkdir(exist_ok=True);(P/'checks/export.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps({**{k:result[k] for k in ['file','sha256','single_printable_body','pass']},
                     'print_ready':{k:ready[k] for k in ['file','sha256','only_black_material','reference_objects','used_vertex_bounds_xyz_mm','volume_cm3','bed_contact']}},indent=2))
if __name__=='__main__':main()
