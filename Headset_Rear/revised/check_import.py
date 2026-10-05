"""Verify new 3MF files with the real Bambu reader, without UI or slicing."""
from pathlib import Path
import argparse
import hashlib
import json
import subprocess
import tempfile

P = Path(__file__).resolve().parent
def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--engine', type=Path, default=Path('D:/Bambu Studio/bambu-studio.exe'))
    args = ap.parse_args()
    startup = subprocess.STARTUPINFO()
    startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    startup.wShowWindow = subprocess.SW_HIDE
    rows = []
    for path in [P/'Rear_Revised_Print_Ready.3mf', P/'Rear_Revised_Wearing.3mf']:
        original = path.read_bytes()
        with tempfile.TemporaryDirectory(prefix='import_', dir=P) as temporary:
            output = Path(temporary)
            cmd = [str(args.engine), '--info', '--debug', '2', '--outputdir', str(output), str(path)]
            result = subprocess.run(cmd, cwd=output, capture_output=True, timeout=45,
                                    startupinfo=startup, creationflags=subprocess.CREATE_NO_WINDOW)
            report = json.loads((output/'result.json').read_text('utf8'))
            assert result.returncode == 0 and report['return_code'] == 0, report
        assert path.read_bytes() == original
        rows.append({'file':path.name, 'sha256':hashlib.sha256(original).hexdigest(),
                     'process_exit_code':result.returncode, 'engine_report':report,
                     'file_unchanged_during_check':True})
        print(path.name+' successfully read.', flush=True)
    evidence = {'engine':str(args.engine), 'mode':'Hidden --info import only; no GUI, no slicing.',
                'files':rows, 'pass':True}
    (P/'checks/import.json').write_text(json.dumps(evidence,indent=2), encoding='utf8')

if __name__ == '__main__':
    main()
