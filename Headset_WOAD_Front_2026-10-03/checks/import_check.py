"""Read delivered archives with Bambu's real importer, without UI or slicing.

An encoding-only regression copy must fail, and each delivered archive must
load successfully. Temporary archives and engine reports are removed on exit.
"""
from pathlib import Path
import argparse, hashlib, json, subprocess, tempfile, zipfile
import xml.etree.ElementTree as ET

P = Path(__file__).resolve().parents[1]
R = P.parent
NS = '{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}'

def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--engine', type=Path, default=Path('D:/Bambu Studio/bambu-studio.exe'))
    args = ap.parse_args()
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    rows = []
    for path in [P/'Front_Print_Ready.3mf', P/'Front_Wearing.3mf', R/'Headset_Rear/Rear_Wearing.3mf']:
        original = path.read_bytes()
        with zipfile.ZipFile(path) as archive:
            assert archive.testzip() is None
            members = [(info, archive.read(info.filename)) for info in archive.infolist()]
            xml = archive.read('3D/3dmodel.model')
        assert b"encoding='UTF-8'" in xml[:100]
        model = ET.fromstring(xml)
        objects = model.findall(NS+'resources/'+NS+'object')
        counts = [{'name':ob.get('name'), 'vertices':len(ob.findall('.//'+NS+'vertex')),
                   'triangles':len(ob.findall('.//'+NS+'triangle'))} for ob in objects]
        assert counts and all(x['vertices'] and x['triangles'] for x in counts)
        trials = {}
        with tempfile.TemporaryDirectory(prefix='import_check_', dir=P) as temporary:
            scratch = Path(temporary)
            regression = scratch/'invalid_encoding.3mf'
            with zipfile.ZipFile(regression, 'w') as archive:
                for info, data in members:
                    if info.filename.endswith('.model'):
                        data = data.replace(b"encoding='UTF-8'", b"encoding='utf8'", 1)
                    archive.writestr(info, data, compresslevel=6)
            for name, input_path in [('regression', regression), ('delivered', path)]:
                output = scratch/name
                output.mkdir()
                cmd = [str(args.engine), '--info', '--debug', '2', '--outputdir', str(output), str(input_path)]
                result = subprocess.run(cmd, cwd=output, capture_output=True, timeout=45,
                                        startupinfo=startup, creationflags=subprocess.CREATE_NO_WINDOW)
                report = json.loads((output/'result.json').read_text('utf8'))
                trials[name] = {'process_exit_code':result.returncode, 'engine_report':report}
            assert trials['regression']['engine_report']['return_code'] == -6
            assert trials['delivered']['process_exit_code'] == 0
            assert trials['delivered']['engine_report']['return_code'] == 0
        assert path.read_bytes() == original
        rows.append({'file':str(path.relative_to(R)).replace('\\','/'),
                     'sha256':hashlib.sha256(original).hexdigest(), 'objects':counts,
                     'encoding_only_regression':trials, 'file_unchanged_during_check':True})
        print(path.name+' successfully read; encoding-only regression rejected.', flush=True)
    proof = {'engine':str(args.engine), 'mode':'Hidden command-line --info: actual 3MF import; no GUI, no slicing.',
             'root_cause':'Bambu importer rejects XML encoding utf8; identical model payload with UTF-8 imports.',
             'files':rows, 'pass':True}
    (P/'checks/import_check.json').write_text(json.dumps(proof,indent=2),encoding='utf8')

if __name__ == '__main__':
    main()
