"""Export assembled references and the real, separately oriented print parts.

Previous finished archives are preserved. All print coordinates are baked into
vertices, so the delivered plate needs no manual object rotation or placement.
"""
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
G = P / 'geometry'
NS = 'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'
ET.register_namespace('', NS)

def tag(name): return '{' + NS + '}' + name
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()

def load(path):
    q = np.load(path)
    v, f = np.asarray(q['v'], float), np.asarray(q['f'], np.int64)
    used = np.unique(f)
    return v[used], np.searchsorted(used, f)

def archive(path, objects, title):
    model = ET.Element(tag('model'), unit='millimeter')
    ET.SubElement(model, tag('metadata'), name='Title').text = title
    resources = ET.SubElement(model, tag('resources'))
    materials = ET.SubElement(resources, tag('basematerials'), id='1')
    for name, color in [('Black_printed_parts', '#23262BFF'),
                        ('Reference_head', '#BEC6C9FF'),
                        ('Reference_camera', '#D6A759FF'),
                        ('Reference_band', '#34383DFF')]:
        ET.SubElement(materials, tag('base'), name=name, displaycolor=color)
    build = ET.SubElement(model, tag('build'))
    for i, (name, v, f, printable, material) in enumerate(objects, 2):
        ob = ET.SubElement(resources, tag('object'), id=str(i),
                           name=name, type='model' if printable else 'other',
                           pid='1', pindex=str(material))
        mesh = ET.SubElement(ob, tag('mesh'))
        vertices = ET.SubElement(mesh, tag('vertices'))
        triangles = ET.SubElement(mesh, tag('triangles'))
        for point in v:
            ET.SubElement(vertices, tag('vertex'), **{
                axis: format(float(value), '.17g') for axis, value in zip('xyz', point)})
        for face in f:
            ET.SubElement(triangles, tag('triangle'), **{
                key: str(int(value)) for key, value in zip(('v1', 'v2', 'v3'), face)})
        ET.SubElement(build, tag('item'), objectid=str(i))
    members = {
        '[Content_Types].xml': b'<?xml version="1.0"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>',
        '_rels/.rels': b'<?xml version="1.0"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>',
        '3D/3dmodel.model': ET.tostring(model, encoding='UTF-8', xml_declaration=True),
    }
    with zipfile.ZipFile(path, 'w') as output:
        for name, raw in members.items():
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            output.writestr(info, raw, compresslevel=6)
    with zipfile.ZipFile(path) as output:
        assert output.testzip() is None
        back = ET.fromstring(output.read('3D/3dmodel.model'))
    rows = back.findall(tag('resources') + '/' + tag('object'))
    assert len(rows) == len(objects)
    for row, (_, v, f, _, _) in zip(rows, objects):
        bv = np.array([[float(pt.get(k)) for k in 'xyz'] for pt in row.findall('.//' + tag('vertex'))])
        bf = np.array([[int(pt.get(k)) for k in ('v1','v2','v3')] for pt in row.findall('.//' + tag('triangle'))])
        assert np.array_equal(bv, v) and np.array_equal(bf, f)
    return {'file': path.name, 'sha256': sha(path),
            'print_objects': sum(obj[3] for obj in objects),
            'reference_objects': sum(not obj[3] for obj in objects),
            'readback_exact': True}

