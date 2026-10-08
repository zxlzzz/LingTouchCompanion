"""Export new rear files only: one printer body and one wearing reference assembly."""
from pathlib import Path
import hashlib
import json
import zipfile
import xml.etree.ElementTree as ET
import numpy as np
import manifold3d as md

P = Path(__file__).resolve().parent
BASE = P.parent
ROOT = BASE.parent
NS = 'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'
ET.register_namespace('', NS)
def tag(name): return '{'+NS+'}'+name
def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def archive(path, objects, title):
    model = ET.Element(tag('model'), unit='millimeter')
    ET.SubElement(model, tag('metadata'), name='Title').text = title
    resources = ET.SubElement(model, tag('resources'))
    build = ET.SubElement(model, tag('build'))
    for index,(name,v,f,printable) in enumerate(objects, 1):
        obj = ET.SubElement(resources, tag('object'), id=str(index), type='model' if printable else 'other', name=name)
        mesh = ET.SubElement(obj, tag('mesh'))
        vs = ET.SubElement(mesh, tag('vertices'))
        ts = ET.SubElement(mesh, tag('triangles'))
        for p in v:
            ET.SubElement(vs, tag('vertex'), x=format(p[0],'.17g'), y=format(p[1],'.17g'), z=format(p[2],'.17g'))
        for t in f:
            ET.SubElement(ts, tag('triangle'), v1=str(t[0]), v2=str(t[1]), v3=str(t[2]))
        ET.SubElement(build, tag('item'), objectid=str(index))
    members = {
        '[Content_Types].xml': b'<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>',
        '_rels/.rels': b'<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>',
        '3D/3dmodel.model': ET.tostring(model, encoding='UTF-8', xml_declaration=True),
    }
    with zipfile.ZipFile(path,'w') as ar:
        for name,data in members.items():
            info = zipfile.ZipInfo(name, (1980,1,1,0,0,0))
            info.compress_type = zipfile.ZIP_DEFLATED
            ar.writestr(info,data,compresslevel=6)
    with zipfile.ZipFile(path) as ar:
        assert ar.testzip() is None
        check = ET.fromstring(ar.read('3D/3dmodel.model'))
    back_objects = check.findall(tag('resources')+'/'+tag('object'))
    assert len(back_objects) == len(objects)
    for back,(_,v,f,_) in zip(back_objects,objects):
        bv = np.array([[float(p.get(k)) for k in 'xyz'] for p in back.findall('.//'+tag('vertex'))])
        bf = np.array([[int(p.get(k)) for k in ['v1','v2','v3']] for p in back.findall('.//'+tag('triangle'))])
        assert np.array_equal(bv,v) and np.array_equal(bf,f)
    return {'file': path.name, 'sha256': digest(path), 'printable_objects': 1,
            'reference_objects': len(objects)-1, 'coordinates_and_indices_readback_exact': True}

def main():
    values = json.loads((P/'geometry/geometry_values.json').read_text(encoding='utf8'))
    rear = np.load(P/'geometry/rear_body.npz'); v,f = rear['v'],rear['f']
    head = np.load(ROOT/'Headset_Inputs/Medium_Trial_Registered.npz')
    battery = np.load(BASE/'geometry/battery.npz')
    wearing = archive(P/'Rear_Revised_Wearing.3mf', [
        ('PRINT_Rear_closed_connector', v,f,True),
        ('REFERENCE_Head_do_not_print', head['v'],head['f'],False),
        ('REFERENCE_Battery_do_not_print', battery['v'],battery['f'],False),
    ], 'Rear with closed connector - wearing coordinates')
    # Original bottom is a genuine flat plane; keep the battery mouth upwards.
    posed = v.copy()
    translation = np.array([128-(v[:,0].min()+v[:,0].max())/2,
                            128-(v[:,1].min()+v[:,1].max())/2, -v[:,2].min()])
    posed += translation
    ready = archive(P/'Rear_Revised_Print_Ready.3mf', [('PRINT_Rear_closed_connector',posed,f,True)], 'Rear with closed connector - ready to print')
    body = md.Manifold(md.Mesh64(vert_properties=np.ascontiguousarray(posed),tri_verts=np.ascontiguousarray(f,dtype=np.uint64)))
    assert body.status() == md.Error.NoError and len(body.decompose()) == 1
    assert abs(body.volume()/1000-values['new_volume_cm3']) < 1e-8
    contact = np.max(np.abs(posed[f][:,:,2]),axis=1) < 1e-7
    bed = posed[f[contact]]
    area = np.linalg.norm(np.cross(bed[:,1]-bed[:,0],bed[:,2]-bed[:,0]),axis=1).sum()/2
    assert area > 100
    ready.update(translation_mm=translation.tolist(), rotation='None; original flat bottom on bed, open mouth up.',
                 bounds_xyz_mm=[posed.min(0).tolist(),posed.max(0).tolist()],
                 bed_contact_area_mm2=float(area),volume_cm3=float(body.volume())/1000)
    result = {'wearing':wearing,'print_ready':ready,'pass':True}
    (P/'checks/export.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps(result,indent=2))

if __name__ == '__main__':
    main()
