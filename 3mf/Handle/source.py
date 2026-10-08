"""Read the original two-object handle project, including production links."""
from pathlib import Path
import hashlib
import posixpath
import xml.etree.ElementTree as ET
import zipfile
import numpy as np

P = Path(__file__).resolve().parent
SOURCE = P / 'inputs/Handle_Original.3mf'
SHA256 = '25cd55ec492a72cccf81dd1d16a50490106574b93a2b63005601ec6ab786d6c6'
NS = '{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}'
PRODUCTION = '{http://schemas.microsoft.com/3dmanufacturing/production/2015/06}'
ROOT_MODEL = '3D/3dmodel.model'


def transform(raw):
    if not raw:
        return np.eye(4)
    values = np.fromstring(raw, sep=' ')
    assert len(values) == 12 and np.isfinite(values).all()
    # 3MF's 4x3 row-vector transform -> homogeneous column-vector matrix.
    return np.vstack([values.reshape(4, 3).T, [0, 0, 0, 1]])


def apply(v, matrix):
    return v @ matrix[:3, :3].T + matrix[:3, 3]


def read_source(path=SOURCE, require_source_hash=True):
    path = Path(path)
    if require_source_hash:
        assert hashlib.sha256(path.read_bytes()).hexdigest() == SHA256, 'Original handle source changed'
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None
        members = {name: archive.read(name) for name in archive.namelist()}
    documents = {}
    def document(name):
        if name not in documents:
            root = ET.fromstring(members[name])
            assert root.get('unit', 'millimeter') == 'millimeter'
            documents[name] = root
        return documents[name]
    def resolve(name, object_id, seen=()):
        key = (name, object_id)
        assert key not in seen, 'Cyclic component graph'
        objects = {o.get('id'): o for o in document(name).findall(NS+'resources/'+NS+'object')}
        obj = objects[object_id]
        mesh = obj.find(NS+'mesh')
        if mesh is not None:
            v = np.array([[float(n.get(k)) for k in 'xyz']
                          for n in mesh.findall(NS+'vertices/'+NS+'vertex')], dtype=np.float64)
            f = np.array([[int(n.get(k)) for k in ('v1','v2','v3')]
                          for n in mesh.findall(NS+'triangles/'+NS+'triangle')], dtype=np.int64)
            assert len(v) and len(f) and np.isfinite(v).all() and f.min()>=0 and f.max()<len(v)
            return [{'model_entry': name, 'mesh_object_id': object_id,
                     'v': v, 'f': f, 'component_transform': np.eye(4)}]
        results = []
        for component in obj.findall(NS+'components/'+NS+'component'):
            child = component.get(PRODUCTION+'path', name)
            child = child.lstrip('/') if child.startswith('/') else (
                name if child == name else posixpath.normpath(posixpath.join(posixpath.dirname(name), child)))
            matrix = transform(component.get('transform'))
            for leaf in resolve(child, component.get('objectid'), seen+(key,)):
                leaf['component_transform'] = matrix @ leaf['component_transform']
                results.append(leaf)
        return results
    root = document(ROOT_MODEL)
    items = root.findall(NS+'build/'+NS+'item')
    assert len(items) == 2, 'Expected the two original handle model objects'
    rows = []
    for index, item in enumerate(items):
        leaves = resolve(ROOT_MODEL, item.get('objectid'))
        assert len(leaves) == 1
        row = leaves[0]
        row.update(name=('housing','cover')[index], build_object_id=item.get('objectid'),
                   printable=item.get('printable','1'), build_transform=transform(item.get('transform')))
        row['native_to_print'] = row['build_transform'] @ row['component_transform']
        rows.append(row)
    return rows, members
