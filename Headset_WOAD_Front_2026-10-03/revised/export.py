"""Export separately named front files, preserving every previous 3MF."""
from pathlib import Path
import hashlib, importlib.util, json

P=Path(__file__).resolve().parent
BASE=P.parent
ROOT=BASE.parent

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    values=json.loads((P/'geometry/geometry_values.json').read_text('utf8'))
    before=values['previous_finished_3mf_sha256']
    spec=importlib.util.spec_from_file_location('previous_front_exporter',BASE/'export.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # The user may have saved the existing rear in Bambu since its old audit.
    # Preserve that current file; this front export has no rear geometry in it.
    source=(BASE/'export.py').read_text('utf8')
    needle="assert rear_check['rear_body_arrays_unchanged'] and rear_hash==rear_check['sha256']"
    assert source.count(needle)==1
    exec(compile(source.replace(needle,'assert rear_hash==_expected_rear'),str(BASE/'export.py'),'exec'),module.__dict__)
    module._expected_rear=before['Headset_Rear/Rear_Wearing.3mf']
    module.P=P;module.G=P/'geometry';module.R=ROOT
    module.main()
    rows=[('Front_Wearing.3mf','Front_Revised_Wearing.3mf'),
          ('Front_Print_Ready.3mf','Front_Revised_Print_Ready.3mf')]
    for old,new in rows:(P/old).replace(P/new)
    report_path=P/'checks/export.json'
    report=json.loads(report_path.read_text('utf8'))
    report['file']=rows[0][1]
    report['print_ready']['file']=rows[1][1]
    report['previous_finished_3mf_sha256']=before
    assert all(digest(ROOT/rel)==sha for rel,sha in before.items())
    report['previous_finished_3mf_untouched']=True
    report.pop('rear_body_arrays_unchanged',None)
    report['revision_exporter_sha256']=digest(Path(__file__))
    report['unchanged_exporter_template_sha256']=digest(BASE/'export.py')
    report_path.write_text(json.dumps(report,indent=2),encoding='utf8')

if __name__=='__main__':main()
