"""Reproduce the PCB STEP with only the U31-U45 and U48 sockets removed."""
import argparse
import hashlib
import math
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE / 'inputs' / '3D_PCB1_5_2026-09-15.step'
OUTPUT = HERE / '3D_PCB1_5_2026-09-15_no_U31-U45_U48_headers.step'
SOURCE_SHA256 = 'bc137079b08c6e28868dd377544d98e749a99668405f34cabf4c29b9ed15f2aa'
TARGET_NAMES = {f'U{i}' for i in range(31, 46)} | {'U48'}
ENTITY_RE = re.compile(rb'#(\d+)\s*=\s*(.*?);', re.S)

def entities(data):
    result = {int(m[1]): m for m in ENTITY_RE.finditer(data)}
    assert len(result) == len(list(ENTITY_RE.finditer(data))), 'Duplicate entity ID'
    return result

def generate():
    original = SOURCE.read_bytes()
    assert hashlib.sha256(original).hexdigest() == SOURCE_SHA256, 'Source baseline changed'
    before = entities(original)
    # These are the 16 placements and their now-unused shared socket BREP.
    # Check all incoming references before deleting the complete model block.
    removed = {n for n in before if 234815 <= n < 261189}
    assert len(removed) == 26370
    products = [before[n][2] for n in removed if before[n][2].startswith(b'PRODUCT(')]
    assert len(products) == 17  # 16 instances plus their shared model definition
    assert {re.search(rb"PRODUCT\('(U\d+)~", p)[1].decode() for p in products
            if re.search(rb"PRODUCT\('(U\d+)~", p)} == TARGET_NAMES
    assert all(b'module~HDR-TH_12P-P1.27-V-F~' in p for p in products)
    placements = set(range(260769, 261175, 27)) | {260757}
    incoming = {
        (n, int(ref))
        for n, m in before.items() if n not in removed
        for ref in re.findall(rb'#(\d+)', m[2]) if int(ref) in removed
    }
    assert incoming == {(10, n) for n in placements}, 'Unexpected shared references'
    root = before[10][0]
    for n in placements:
        root, count = re.subn(rb',\s*#' + str(n).encode() + rb'\b', b'', root)
        assert count == 1
    replacements = [(before[n].start(), before[n].end(), b'') for n in removed]
    replacements.append((before[10].start(), before[10].end(), root))
    chunks, offset = [], 0
    for start, end, replacement in sorted(replacements):
        chunks.extend((original[offset:start], replacement))
        offset = end
    chunks.append(original[offset:])
    output = b''.join(chunks)
    after = entities(output)
    assert set(before) - set(after) == removed
    assert not (set(after) - set(before))
    assert {n for n in after if before[n][0] != after[n][0]} == {10}
    for m in after.values():
        assert all(int(ref) in after for ref in re.findall(rb'#(\d+)', m[2])), 'Dangling STEP reference'
    assert b"PRODUCT('U46~SOIC-16" in output
    assert b"PRODUCT('U47~SOP-16" in output
    assert b'HDR-TH_12P-P1.27-V-F' not in output
    OUTPUT.write_bytes(output)
    assert SOURCE.read_bytes() == original
    print(f'Created {OUTPUT.name}: removed 16 socket instances (U31-U45 and U48); U46 and U47 retained.')
    print('All remaining STEP entity records are byte-identical, except the root placement list.')

def verify_cad():
    from OCP.STEPCAFControl import STEPCAFControl_Reader
    from OCP.XCAFDoc import XCAFDoc_DocumentTool
    from OCP.TDocStd import TDocStd_Document
    from OCP.TCollection import TCollection_ExtendedString
    from OCP.collections import Sequence_TDF_Label
    from OCP.TDataStd import TDataStd_Name
    from OCP.TDF import TDF_Label
    from OCP.BRepGProp import BRepGProp
    from OCP.GProp import GProp_GProps
    from OCP.BRepBndLib import BRepBndLib
    from OCP.Bnd import Bnd_Box
    from OCP.TopAbs import TopAbs_SOLID, TopAbs_FACE, TopAbs_EDGE
    from OCP.TopExp import TopExp_Explorer
    from OCP.IFSelect import IFSelect_RetDone

    def snapshot(path):
        reader = STEPCAFControl_Reader()
        reader.SetNameMode(True)
        assert reader.ReadFile(str(path)) == IFSelect_RetDone
        doc = TDocStd_Document(TCollection_ExtendedString('pcb'))
        assert reader.Transfer(doc)
        tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
        roots, parts = Sequence_TDF_Label(), Sequence_TDF_Label()
        tool.GetFreeShapes(roots)
        assert roots.Length() == 1
        assert tool.GetComponents_s(roots.Value(1), parts, False)
        result = {}
        for i in range(1, parts.Length()+1):
            label, referred = parts.Value(i), TDF_Label()
            assert tool.GetReferredShape_s(label, referred)
            attr = TDataStd_Name()
            assert referred.FindAttribute(TDataStd_Name.GetID_s(), attr)
            name = attr.Get().ToExtString()
            assert name not in result
            shape = tool.GetShape_s(label)
            counts = []
            for kind in (TopAbs_SOLID, TopAbs_FACE, TopAbs_EDGE):
                explorer = TopExp_Explorer(shape, kind)
                count = 0
                while explorer.More():
                    count += 1
                    explorer.Next()
                counts.append(count)
            props = GProp_GProps()
            BRepGProp.VolumeProperties_s(shape, props)
            center = props.CentreOfMass()
            box = Bnd_Box()
            BRepBndLib.Add_s(shape, box)
            if box.IsVoid():
                assert counts == [0, 0, 0]
                bounds = ()
            else:
                low, high = box.CornerMin(), box.CornerMax()
                bounds = (low.X(), low.Y(), low.Z(), high.X(), high.Y(), high.Z())
            values = (props.Mass(), center.X(), center.Y(), center.Z()) + bounds
            result[name] = (counts, values)
        return result

    before, after = snapshot(SOURCE), snapshot(OUTPUT)
    expected_removed = {n for n in before if n.split('~')[0] in TARGET_NAMES}
    assert len(expected_removed) == 16
    assert set(before) - set(after) == expected_removed
    assert not (set(after) - set(before))
    for name in after:
        assert before[name][0] == after[name][0], f'Topology changed: {name}'
        assert len(before[name][1]) == len(after[name][1]), f'Bounds changed: {name}'
        assert all(math.isclose(a, b, rel_tol=1e-12, abs_tol=1e-9)
                   for a, b in zip(before[name][1], after[name][1])), f'Geometry changed: {name}'
    assert len(before) == 179 and len(after) == 163
    print('CAD verification passed: 179 -> 163 top-level objects; all 163 retained objects match.')

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--verify', action='store_true', help='Verify CAD geometry using cadquery-ocp 8.0.1.1.0')
    args = parser.parse_args()
    generate()
    if args.verify:
        verify_cad()
