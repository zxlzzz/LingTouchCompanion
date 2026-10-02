"""Inspect the supplied STEP assemblies without changing source geometry."""
from pathlib import Path
import hashlib
import json
import numpy as np
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.TDocStd import TDocStd_Document
from OCP.TCollection import TCollection_ExtendedString
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from OCP.TDF import TDF_Label
try:
    from OCP.TDF import TDF_LabelSequence
except ImportError:
    from OCP.collections import Sequence_TDF_Label as TDF_LabelSequence
from OCP.TDataStd import TDataStd_Name
from OCP.TopLoc import TopLoc_Location
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRep import BRep_Tool
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE, TopAbs_REVERSED
from OCP.TopoDS import TopoDS
from OCP.IFSelect import IFSelect_RetDone

HERE = Path(__file__).resolve().parent
REF = HERE.parent / 'glasses_refs' / 'cs30_radxa'

def bounds(shape):
    box = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, box, False, False)
    if box.IsVoid():
        return None
    lo, hi = box.CornerMin(), box.CornerMax()
    return [lo.X(), lo.Y(), lo.Z(), hi.X(), hi.Y(), hi.Z()]

def label_name(label):
    attribute = TDataStd_Name()
    if label.FindAttribute(TDataStd_Name.GetID_s(), attribute):
        return attribute.Get().ToExtString()
    return ''

def mesh(shape):
    BRepMesh_IncrementalMesh(shape, .18, False, .25, True).Perform()
    vertices, triangles = [], []
    explorer = TopExp_Explorer(shape, TopAbs_FACE)
    while explorer.More():
        face = TopoDS.Face(explorer.Current())
        location = TopLoc_Location()
        triangulation = BRep_Tool.Triangulation_s(face, location)
        if triangulation is not None:
            offset = len(vertices)
            transform = location.Transformation()
            for i in range(1, triangulation.NbNodes()+1):
                p = triangulation.Node(i).Transformed(transform)
                vertices.append([p.X(), p.Y(), p.Z()])
            for i in range(1, triangulation.NbTriangles()+1):
                a, b, c = triangulation.Triangle(i).Get()
                if face.Orientation() == TopAbs_REVERSED:
                    b, c = c, b
                triangles.append([offset+a-1, offset+b-1, offset+c-1])
        explorer.Next()
    return np.array(vertices), np.array(triangles, dtype=np.int32)

def inspect(path, key):
    reader = STEPCAFControl_Reader()
    reader.SetNameMode(True)
    reader.SetColorMode(False)
    if reader.ReadFile(str(path)) != IFSelect_RetDone:
        raise RuntimeError(f'Cannot read {path}')
    document = TDocStd_Document(TCollection_ExtendedString('MDTV-XCAF'))
    if not reader.Transfer(document):
        raise RuntimeError('STEP transfer failed')
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(document.Main())
    roots = TDF_LabelSequence()
    shape_tool.GetFreeShapes(roots)
    leaves, all_vertices, all_faces = [], [], []
    offset = 0
    def walk(label, location, parents):
        nonlocal offset
        name = label_name(label)
        if shape_tool.IsReference_s(label):
            referred = TDF_Label()
            shape_tool.GetReferredShape_s(label, referred)
            walk(referred, location.Multiplied(shape_tool.GetLocation_s(label)), parents + [name])
            return
        components = TDF_LabelSequence()
        if shape_tool.GetComponents_s(label, components, False):
            for index in range(1, components.Length()+1):
                walk(components.Value(index), location, parents + [name])
            return
        shape = shape_tool.GetShape_s(label).Moved(location)
        if shape.IsNull():
            return
        box = bounds(shape)
        if box is None:
            return
        v, f = mesh(shape)
        leaves.append({'name': name, 'parents': parents, 'bounds': box,
                       'size': list(np.array(box[3:])-np.array(box[:3])),
                       'vertex_range': [offset, offset+len(v)]})
        all_vertices.append(v)
        all_faces.append(f+offset)
        offset += len(v)
    for index in range(1, roots.Length()+1):
        walk(roots.Value(index), TopLoc_Location(), [])
    vertices = np.concatenate(all_vertices)
    faces = np.concatenate(all_faces)
    np.savez_compressed(HERE/f'{key}_official_mesh.npz', vertices=vertices, faces=faces)
    result = {'source': str(path), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
              'mesh_bounds': [vertices.min(0).tolist(), vertices.max(0).tolist()],
              'leaves': leaves}
    (HERE/f'{key}_step_measurements.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    important = [row for row in leaves if any(term in row['name'].upper() for term in
                 ['CASE', 'LENS', 'GLASS', 'USB', 'SHELL', 'HSG', 'PCB', 'LED', 'IR_', 'WINDOW'])]
    print(key, 'mesh bounds', result['mesh_bounds'], 'leaves', len(leaves), 'triangles', len(faces))
    print(json.dumps(important, ensure_ascii=False, indent=2)[:14000])

if __name__ == '__main__':
    inspect(REF/'CS30_official.stp', 'camera')
    inspect(REF/'Radxa_ZERO3W_v1.11_official.stp', 'board')
