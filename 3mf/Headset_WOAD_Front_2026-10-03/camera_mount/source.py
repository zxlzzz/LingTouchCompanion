"""Read the retained final, single-body, millimetre 3MF without repairing it."""
from pathlib import Path
import hashlib
import xml.etree.ElementTree as ET
import zipfile
import numpy as np

P = Path(__file__).resolve().parent
SOURCE = P.parent.parent / 'Headset_Inputs' / 'Front_CS30_Mount_Final.3mf'
SOURCE_SHA256 = 'ef1406f50a50c62fd6e395560f89924b7d319fddc9b5e95bdd94fbafb40aea61'
NS = '{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}'
MODEL_ENTRY = '3D/3dmodel.model'
SETTINGS_ENTRY = 'Metadata/project_settings.config'


def read_source(path=SOURCE, check_digest=True):
    path = Path(path)
    if check_digest:
        assert hashlib.sha256(path.read_bytes()).hexdigest() == SOURCE_SHA256, 'Final source changed'
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        members = {name: archive.read(name) for name in archive.namelist()}
    root = ET.fromstring(members[MODEL_ENTRY])
    assert root.get('unit', 'millimeter') == 'millimeter'
    objects = root.findall(NS + 'resources/' + NS + 'object')
    items = root.findall(NS + 'build/' + NS + 'item')
    assert len(objects) == len(items) == 1, 'Expected the retained single printable body'
    obj, item = objects[0], items[0]
    assert obj.get('type', 'model') == 'model' and item.get('objectid') == obj.get('id')
    assert obj.find(NS + 'components') is None
    if item.get('transform'):
        assert np.array_equal(np.fromstring(item.get('transform'), sep=' '),
                              [1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0]), 'Unexpected build transform'
    mesh = obj.find(NS + 'mesh')
    assert mesh is not None
    v = np.array([[float(node.get(key)) for key in 'xyz']
                  for node in mesh.findall(NS + 'vertices/' + NS + 'vertex')], dtype=np.float64)
    f = np.array([[int(node.get(key)) for key in ('v1', 'v2', 'v3')]
                  for node in mesh.findall(NS + 'triangles/' + NS + 'triangle')], dtype=np.int64)
    assert len(v) and len(f) and np.isfinite(v).all() and f.min() >= 0 and f.max() < len(v)
    return v, f, members
