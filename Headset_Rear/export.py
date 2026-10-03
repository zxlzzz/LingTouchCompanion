"""Export the unchanged rear with registered head and battery references.

The delivered Rear_Wearing.3mf is the original byte-for-byte container copy.
Use --verify-existing to verify it without rewriting. Running without that
flag regenerates the container while preserving all mesh coordinates exactly.
"""
from pathlib import Path
import argparse,hashlib,json,zipfile
import xml.etree.ElementTree as ET
import numpy as np
import manifold3d as md

P=Path(__file__).resolve().parent;G=P/'geometry';R=P.parent
NS='http://schemas.microsoft.com/3dmanufacturing/core/2015/02'
ET.register_namespace('',NS)
def tag(s):return '{'+NS+'}'+s
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def arrays(q):
    return {k:hashlib.sha256(np.ascontiguousarray(q[k]).tobytes()).hexdigest() for k in ['v','f']}
PATHS=[('PRINT_Rear_shell',G/'rear_body.npz',True),
       ('REFERENCE_Head_do_not_print',R/'Headset_Inputs/Medium_Trial_Registered.npz',False),
       ('REFERENCE_Battery_do_not_print',G/'battery.npz',False)]

def verify(path):
    with zipfile.ZipFile(path) as ar:back=ET.fromstring(ar.read('3D/3dmodel.model'))
    objects=back.findall(tag('resources')+'/'+tag('object'))
    assert len(objects)==len(PATHS)
    items=back.findall(tag('build')+'/'+tag('item'));assert len(items)==len(PATHS)
    assert all('transform' not in it.attrib for it in items),'Wearing coordinates transformed'
    rows=[]
    for ob,(name,source,printable) in zip(objects,PATHS):
        q=np.load(source)
        v=np.array([[float(p.get(k)) for k in 'xyz'] for p in ob.findall('.//'+tag('vertex'))])
        f=np.array([[int(p.get(k)) for k in ['v1','v2','v3']] for p in ob.findall('.//'+tag('triangle'))])
        error=float(np.max(np.abs(v-q['v'])))
        assert error<1e-8 and np.array_equal(f,q['f']),name
        assert ob.get('type')==('model' if printable else 'other'),name
        row={'name':ob.get('name'),'printable':printable,'source':str(source.relative_to(R)).replace('\\','/'),
             'source_sha256':digest(source),'array_sha256':arrays(q),'vertices':len(v),'triangles':len(f),
             'maximum_container_coordinate_roundoff_mm':error,
             'bounds_xyz_mm':[v.min(0).tolist(),v.max(0).tolist()]}
        if printable:
            m=md.Manifold(md.Mesh64(vert_properties=np.ascontiguousarray(v,dtype=np.float64),tri_verts=np.ascontiguousarray(f,dtype=np.uint64)))
            assert m.status()==md.Error.NoError and len(m.decompose())==1
            row.update(single_closed_connected_solid=True,volume_cm3=float(m.volume())/1000)
        rows.append(row)
    original=json.loads((P/'source_provenance.json').read_text(encoding='utf8'))
    assert rows[0]['array_sha256']==original['unchanged_meshes']['rear_body']['array_sha256']
    return {'file':path.name,'sha256':digest(path),'wearing_coordinates_preserved':True,
            'rear_body_arrays_unchanged':True,'original_rear_3mf_sha256':original['source_rear_3mf']['sha256'],
            'original_3mf_byte_copy_preserved':digest(path)==original['source_rear_3mf']['sha256'],
            'objects':rows}

def write(path):
    model=ET.Element(tag('model'),unit='millimeter')
    ET.SubElement(model,tag('metadata'),name='Title').text='Unchanged rear assembly - wearing coordinates'
    ET.SubElement(model,tag('metadata'),name='Description').text='Original rear body coordinates and triangles preserved. Head and battery are nonprintable references.'
    resources=ET.SubElement(model,tag('resources'));build=ET.SubElement(model,tag('build'))
    for i,(name,source,printable) in enumerate(PATHS,1):
        q=np.load(source);obj=ET.SubElement(resources,tag('object'),id=str(i),type='model' if printable else 'other',name=name)
        mesh=ET.SubElement(obj,tag('mesh'));vs=ET.SubElement(mesh,tag('vertices'));ts=ET.SubElement(mesh,tag('triangles'))
        for p in q['v']:ET.SubElement(vs,tag('vertex'),x=format(p[0],'.17g'),y=format(p[1],'.17g'),z=format(p[2],'.17g'))
        for p in q['f']:ET.SubElement(ts,tag('triangle'),v1=str(p[0]),v2=str(p[1]),v3=str(p[2]))
        ET.SubElement(build,tag('item'),objectid=str(i))
    members={'[Content_Types].xml':b'<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>',
             '_rels/.rels':b'<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>',
             '3D/3dmodel.model':ET.tostring(model,encoding='utf8',xml_declaration=True)}
    with zipfile.ZipFile(path,'w') as ar:
        for name,data in members.items():
            info=zipfile.ZipInfo(name,(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED
            ar.writestr(info,data,compresslevel=6)

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,default=P/'Rear_Wearing.3mf')
    ap.add_argument('--verify-existing',action='store_true');args=ap.parse_args()
    if not args.verify_existing:write(args.output)
    result=verify(args.output)
    (P/'checks/export.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps({k:result[k] for k in ['file','sha256','rear_body_arrays_unchanged','original_3mf_byte_copy_preserved']},indent=2))
if __name__=='__main__':main()
