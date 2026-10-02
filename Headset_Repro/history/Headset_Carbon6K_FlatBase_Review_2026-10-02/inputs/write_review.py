from pathlib import Path
import hashlib,json,zipfile
import xml.etree.ElementTree as ET
import numpy as np
import manifold3d as md

def write_review(path, source, label):
    with np.load(source, allow_pickle=False) as a:
        v, f = (a['v'], a['f'])
    m = md.Manifold(md.Mesh64(vert_properties=np.ascontiguousarray(v, dtype=np.float64), tri_verts=np.ascontiguousarray(f, dtype=np.uint64)))
    parts_m = m.decompose()
    positive = [p for p in parts_m if p.volume() > 1e-08]
    negative = [p for p in parts_m if p.volume() < -1e-08]
    if m.status() != md.Error.NoError or len(positive) != 1:
        raise ValueError(f'{label}: mesh not a single valid connected solid')
    parts = ['<?xml version="1.0" encoding="UTF-8"?>', '<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">', f'<metadata name="Title">{label} - review only, wearing coordinates</metadata>', '<metadata name="Description">No print rotation or placement. X lateral; Y posterior; Z up.</metadata>', '<resources><object id="1" type="model" name="' + label + '"><mesh><vertices>']
    parts.extend(('<vertex x="%.17g" y="%.17g" z="%.17g"/>' % tuple(p) for p in v))
    parts.append('</vertices><triangles>')
    parts.extend(('<triangle v1="%d" v2="%d" v3="%d"/>' % tuple(p) for p in f))
    parts.append('</triangles></mesh></object></resources><build><item objectid="1"/></build></model>')
    content_types = '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>'
    relations = '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rel0" Target="/3D/3dmodel.model" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>'
    with zipfile.ZipFile(path, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('[Content_Types].xml', content_types)
        z.writestr('_rels/.rels', relations)
        z.writestr('3D/3dmodel.model', ''.join(parts))
    namespace = '{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}'
    with zipfile.ZipFile(path) as z:
        model = ET.fromstring(z.read('3D/3dmodel.model'))
    rv = np.array([[float(p.attrib[k]) for k in ['x', 'y', 'z']] for p in model.findall('.//' + namespace + 'vertex')])
    rf = np.array([[int(p.attrib[k]) for k in ['v1', 'v2', 'v3']] for p in model.findall('.//' + namespace + 'triangle')])
    assert np.array_equal(rv, v) and np.array_equal(rf, f)
    return {'file': str(path), 'source_mesh': str(source.resolve()), 'source_mesh_sha256': hashlib.sha256(source.read_bytes()).hexdigest(), 'file_sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'review_only': True, 'wearing_coordinates_preserved_exactly': True, 'units': 'millimeter', 'single_closed_connected_solid': True, 'connected_positive_solids': len(positive), 'enclosed_air_boundary_shells': len(negative), 'volume_mm3': float(m.volume()), 'bounds_xyz_mm': [v.min(0).tolist(), v.max(0).tolist()]}
