"""Read the reference 3MF and report its actual mesh/build dimensions."""
from pathlib import Path
import json
import zipfile
import xml.etree.ElementTree as ET
import numpy as np

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent/'raw/BTTF_Glasses.3mf'
CORE = '{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}'
PRODUCTION = '{http://schemas.microsoft.com/3dmanufacturing/production/2015/06}'

def transform(text):
    if not text:
        return np.eye(4)
    values = np.array([float(v) for v in text.split()]).reshape(4, 3)
    result = np.eye(4)
    result[:3, :3] = values[:3, :].T
    result[:3, 3] = values[3, :]
    return result

def moved(vertices, matrix):
    return vertices @ matrix[:3, :3].T + matrix[:3, 3]

def main():
    with zipfile.ZipFile(SOURCE) as archive:
        models = {}
        for name in archive.namelist():
            if name.endswith('.model'):
                root = ET.fromstring(archive.read(name))
                models[name] = {o.attrib['id']: o for o in root.findall(CORE+'resources/'+CORE+'object')}
        def flatten(name, object_id):
            obj = models[name][object_id]
            mesh = obj.find(CORE+'mesh')
            if mesh is not None:
                vertices = np.array([[float(v.attrib[a]) for a in ['x', 'y', 'z']]
                     for v in mesh.findall(CORE+'vertices/'+CORE+'vertex')])
                faces = np.array([[int(v.attrib[a]) for a in ['v1', 'v2', 'v3']]
                     for v in mesh.findall(CORE+'triangles/'+CORE+'triangle')], dtype=np.int32)
                return vertices, faces
            vertices, faces, offset = [], [], 0
            for component in obj.findall(CORE+'components/'+CORE+'component'):
                path = component.attrib.get(PRODUCTION+'path', name).lstrip('/')
                v, f = flatten(path, component.attrib['objectid'])
                vertices.append(moved(v, transform(component.attrib.get('transform'))))
                faces.append(f+offset)
                offset += len(v)
            return np.concatenate(vertices), np.concatenate(faces)
        root = ET.fromstring(archive.read('3D/3dmodel.model'))
        report = []
        for item in root.findall(CORE+'build/'+CORE+'item'):
            v, f = flatten('3D/3dmodel.model', item.attrib['objectid'])
            matrix = transform(item.attrib.get('transform'))
            world = moved(v, matrix)
            row = {'object_id': item.attrib['objectid'], 'native_size_mm': np.ptp(v, axis=0).tolist(),
                   'build_size_xyz_mm': np.ptp(world, axis=0).tolist(),
                   'build_axis_scales': np.linalg.norm(matrix[:3,:3],axis=0).tolist(),
                   'triangles': len(f)}
            report.append(row)
            if item.attrib['objectid'] == '2':
                centered = v-(v.min(0)+v.max(0))/2
                # Retain the actual Normal object's axis scales, remove bed placement.
                actual = centered*np.linalg.norm(matrix[:3,:3],axis=0)
                np.savez_compressed(HERE/'reference_normal_mesh.npz',vertices=actual,faces=f)
        for source, target in [
            ('Metadata/plate_1.png', 'reference_plate.png'),
            ('Auxiliaries/Model Pictures/P1155183.webp', 'reference_photo_1.webp'),
            ('Auxiliaries/Model Pictures/P1155193.webp', 'reference_photo_2.webp')]:
            (HERE/target).write_bytes(archive.read(source))
        (HERE/'reference_measurements.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
        print(json.dumps(report,indent=2))

if __name__ == '__main__':
    main()

