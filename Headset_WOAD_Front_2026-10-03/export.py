"""Export separate printable parts and actual references in wearing coordinates."""
from pathlib import Path
import hashlib,json,zipfile
import xml.etree.ElementTree as ET
import numpy as np
import manifold3d as md

P=Path(__file__).resolve().parent;G=P/'geometry';R=P.parent
NS='http://schemas.microsoft.com/3dmanufacturing/core/2015/02'
ET.register_namespace('',NS)
def tag(s):return '{'+NS+'}'+s
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    paths=[('PRINT_Front_shell',G/'front_body.npz',True,'#23262BFF'),
           ('PRINT_Removable_cover',G/'service_lid.npz',True,'#23262BFF'),
           ('PRINT_Blue_bezel_optional',G/'bezel_trim.npz',True,'#3B80B8FF'),
           ('PRINT_TPU_split_cable_gland',G/'cable_gland.npz',True,'#42464AFF'),
           ('REFERENCE_Head_do_not_print',R/'Headset_Carbon6K_FlatBase_Review_2026-10-02/inputs/Medium_Trial_Registered.npz',False,'#BEC6C9FF'),
           ('REFERENCE_Actual_CS30_customer_STEP_do_not_print',G/'camera.npz',False,'#D6A759FF'),
           ('REFERENCE_Four_M3x12_screws_and_M3_nuts_do_not_print',G/'fasteners.npz',False,'#A7AFB8FF'),
           ('REFERENCE_Compressed_soft_pads_do_not_print',G/'pads.npz',False,'#767D85FF')]
    model=ET.Element(tag('model'),unit='millimeter')
    ET.SubElement(model,tag('metadata'),name='Title').text='WOAD-inspired front - wearing assembly'
    ET.SubElement(model,tag('metadata'),name='Description').text='Wearing coordinates unchanged. Four independent printable parts; all named REFERENCE objects are inspection references, not printable parts. Camera is the actual customer STEP geometry. Original rear assembly remains unchanged in its existing directory.'
    resources=ET.SubElement(model,tag('resources'));materials=ET.SubElement(resources,tag('basematerials'),id='1');build=ET.SubElement(model,tag('build'));rows=[]
    for i,(name,path,printable,color) in enumerate(paths):
        ET.SubElement(materials,tag('base'),name=name,displaycolor=color)
        q=np.load(path);v=q['v'];f=q['f'];oid=str(i+2)
        obj=ET.SubElement(resources,tag('object'),id=oid,type='model' if printable else 'other',name=name,pid='1',pindex=str(i))
        me=ET.SubElement(obj,tag('mesh'));vs=ET.SubElement(me,tag('vertices'));ts=ET.SubElement(me,tag('triangles'))
        for p in v:ET.SubElement(vs,tag('vertex'),x=format(p[0],'.12g'),y=format(p[1],'.12g'),z=format(p[2],'.12g'))
        for p in f:ET.SubElement(ts,tag('triangle'),v1=str(p[0]),v2=str(p[1]),v3=str(p[2]))
        ET.SubElement(build,tag('item'),objectid=oid)
        row={'name':name,'printable':printable,'source_sha256':digest(path),'vertices':len(v),'triangles':len(f),'bounds_xyz_mm':[v.min(0).tolist(),v.max(0).tolist()]}
        if printable:
            m=md.Manifold(md.Mesh64(vert_properties=np.ascontiguousarray(v,dtype=np.float64),tri_verts=np.ascontiguousarray(f,dtype=np.uint64)))
            assert m.status()==md.Error.NoError and len(m.decompose())==1,(name,m.status(),len(m.decompose()))
            # Independently inspect every undirected edge of the exported mesh.
            e=np.sort(np.concatenate([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]]),axis=1)
            _,n=np.unique(e,axis=0,return_counts=True);assert (n==2).all(),name
            row.update(volume_cm3=float(m.volume())/1000,closed_connected_manifold=True)
        rows.append(row)
    out=P/'Front_WOAD_Wearing.3mf'
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as ar:
        ar.writestr('[Content_Types].xml','<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
        ar.writestr('_rels/.rels','<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
        ar.writestr('3D/3dmodel.model',ET.tostring(model,encoding='utf8',xml_declaration=True))
    # Read the actual final container and compare coordinates/index arrays.
    with zipfile.ZipFile(out) as ar:
        back=ET.fromstring(ar.read('3D/3dmodel.model'))
        obs=back.findall(tag('resources')+'/'+tag('object'));assert len(obs)==len(paths)
        assert len(back.findall(tag('build')+'/'+tag('item')))==len(paths)
        for ob,(_,path,_,_) in zip(obs,paths):
            q=np.load(path)
            v=np.array([[float(p.get(k)) for k in 'xyz'] for p in ob.findall('.//'+tag('vertex'))])
            f=np.array([[int(p.get(k)) for k in ['v1','v2','v3']] for p in ob.findall('.//'+tag('triangle'))])
            assert np.max(np.abs(v-q['v']))<1e-8 and np.array_equal(f,q['f'])
    result={'file':out.name,'sha256':digest(out),'wearing_coordinates_preserved':True,'object_count':len(paths),'objects':rows,
            'rear_assembly_unchanged_sha256':digest(R/'Headset_Carbon6K_FlatBase_Review_2026-10-02/Rear_Carbon6K_FlatBase_Review_Wearing.3mf')}
    (P/'checks/export.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    print(out.name,result['sha256'],len(paths))

if __name__=='__main__':main()
