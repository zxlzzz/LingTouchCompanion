"""Export the finished front in its actual saved print pose and settings."""
import hashlib
import json
import shutil
import xml.etree.ElementTree as ET
import zipfile
import numpy as np
from source import P, SOURCE, NS, MODEL_ENTRY, SETTINGS_ENTRY, read_source


def main():
    original_v, original_f, members = read_source()
    with np.load(P / 'geometry/front_print.npz') as data:
        v, f = data['v'], data['f']
    unchanged = np.array_equal(v, original_v) and np.array_equal(f, original_f)
    path = P / 'Front_CS30_Mount_Print.3mf'
    if unchanged:
        # Preserve every saved byte, including all metadata and print settings.
        # The output is never used as its own input.
        shutil.copyfile(SOURCE, path)
    else:
        ET.register_namespace('', NS[1:-1])
        root = ET.fromstring(members[MODEL_ENTRY])
        mesh = root.find(NS + 'resources/' + NS + 'object/' + NS + 'mesh')
        mesh.clear()
        vertices = ET.SubElement(mesh, NS + 'vertices')
        triangles = ET.SubElement(mesh, NS + 'triangles')
        for point in v:
            ET.SubElement(vertices, NS + 'vertex', **{
                key: format(float(value), '.17g') for key, value in zip('xyz', point)})
        for face in f:
            ET.SubElement(triangles, NS + 'triangle', **{
                key: str(int(value)) for key, value in zip(('v1', 'v2', 'v3'), face)})
        members[MODEL_ENTRY] = ET.tostring(root, encoding='UTF-8', xml_declaration=True)
        with zipfile.ZipFile(path, 'w', compression=zipfile.ZIP_DEFLATED) as archive:
            for name, raw in members.items():
                archive.writestr(name, raw)
    bv, bf, back = read_source(path, check_digest=False)
    assert np.array_equal(bv, v) and np.array_equal(bf, f)
    assert back[SETTINGS_ENTRY] == members[SETTINGS_ENTRY]
    report = {'file': path.name, 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(),
              'single_print_body': True, 'readback_exact': True,
              'whole_archive_identical_to_finished_source': unchanged,
              'saved_print_settings_bytes_preserved': True,
              'print_bounds_xyz_mm': [v.min(0).tolist(), v.max(0).tolist()]}
    (P / 'checks/export.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
