"""Export both review assemblies, retaining all wearing coordinates."""
from pathlib import Path
import json, hashlib, zipfile
import xml.etree.ElementTree as ET
import numpy as np
import manifold3d as md

P=Path(__file__).resolve().parent
R=P.parent/'Headset_Carbon6K_FlatBase_Review_2026-10-02'
NS='http://schemas.microsoft.com/3dmanufacturing/core/2015/02'
ET.register_namespace('',NS)
def tag(n):return '{'+NS+'}'+n
def export(folder, filename, shell, occupant, label):
    model=ET.Element(tag('model'),unit='millimeter')
    ET.SubElement(model,tag('metadata'),name='Title').text=label+' - inspection assembly'
    ET.SubElement(model,tag('metadata'),name='Description').text='Review only. Shell is the printable candidate; head and occupant are separate inspection references. Wearing coordinates retained. Do not print the reference objects.'
    resources=ET.SubElement(model,tag('resources'))
    colors=ET.SubElement(resources,tag('basematerials'),id='1')
    for name,color in [('shell','#218D9FFF'),('head reference','#CCCCCCFF'),('occupant reference','#EB9C34FF')]:
        ET.SubElement(colors,tag('base'),name=name,displaycolor=color)
    build=ET.SubElement(model,tag('build')); report=[]
    for i,(name,path) in enumerate([(label+'_shell',shell),('Head_reference_do_not_print',R/'inputs/Medium_Trial_Registered.npz'),(label+'_occupant_reference_do_not_print',occupant)],2):
        a=np.load(path);v=a['v'];f=a['f'];typ='model' if i==2 else 'other'
        obj=ET.SubElement(resources,tag('object'),id=str(i),type=typ,name=name,pid='1',pindex=str(i-2))
        mesh=ET.SubElement(obj,tag('mesh'));vs=ET.SubElement(mesh,tag('vertices'));ts=ET.SubElement(mesh,tag('triangles'))
        for q in v:ET.SubElement(vs,tag('vertex'),x=format(q[0],'.12g'),y=format(q[1],'.12g'),z=format(q[2],'.12g'))
        for q in f:ET.SubElement(ts,tag('triangle'),v1=str(q[0]),v2=str(q[1]),v3=str(q[2]))
        ET.SubElement(build,tag('item'),objectid=str(i))
        entry={'name':name,'type':typ,'bounds_xyz_mm':[v.min(0).tolist(),v.max(0).tolist()],'vertices':len(v),'triangles':len(f),'source_sha256':hashlib.sha256(path.read_bytes()).hexdigest()}
        if i==2:
            m=md.Manifold(md.Mesh64(vert_properties=v,tri_verts=f.astype(np.uint64)))
            assert m.status()==md.Error.NoError and len(m.decompose())==1
            entry['single_closed_connected_solid']=True;entry['volume_cm3']=m.volume()/1000
        report.append(entry)
    output=folder/filename
    with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        z.writestr('[Content_Types].xml','<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
        z.writestr('_rels/.rels','<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
        z.writestr('3D/3dmodel.model',ET.tostring(model,encoding='utf8',xml_declaration=True))
    with zipfile.ZipFile(output) as z:
        xml=ET.fromstring(z.read('3D/3dmodel.model'));objects=xml.findall('.//'+tag('object'))
        assert len(objects)==3 and len(xml.findall('.//'+tag('item')))==3
        for ob,entry in zip(objects,report):
            coords=np.array([[float(q.attrib[k]) for k in ('x','y','z')] for q in ob.findall('.//'+tag('vertex'))])
            assert np.allclose([coords.min(0),coords.max(0)],entry['bounds_xyz_mm'],atol=1e-8)
    result={'review_only':True,'wearing_coordinates_preserved':True,'independent_object_count':3,'objects':report,'filename':str(output)}
    (folder/'model_verification.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    print(filename,len(objects),report[0]['volume_cm3'])
if __name__=='__main__':
    export(P,'Front_Compact_Review_Wearing.3mf',P/'geometry/front_unified_preview.npz',P/'geometry/camera.npz','Front_Compact_Review')
    export(R,'Rear_Carbon6K_FlatBase_Review_Wearing.3mf',R/'geometry/rear_unified_preview.npz',R/'geometry/battery_preview.npz','Rear_Carbon6K_top_open_flat_base')
