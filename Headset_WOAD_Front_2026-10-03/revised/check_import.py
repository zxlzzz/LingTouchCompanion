"""Verify the separately saved front with Bambu's importer, without slicing/UI."""
from pathlib import Path
import hashlib,json,subprocess,tempfile

P=Path(__file__).resolve().parent
ENGINE=Path('D:/Bambu Studio/bambu-studio.exe')

def main():
    startup=subprocess.STARTUPINFO();startup.dwFlags|=subprocess.STARTF_USESHOWWINDOW;startup.wShowWindow=subprocess.SW_HIDE
    results=[]
    for name in ('Front_Revised_Print_Ready.3mf','Front_Revised_Wearing.3mf'):
        path=P/name;data=path.read_bytes()
        with tempfile.TemporaryDirectory(prefix='front_import_',dir=P) as temporary:
            scratch=Path(temporary)
            proc=subprocess.run([str(ENGINE),'--info','--debug','2','--outputdir',str(scratch),str(path)],
                cwd=scratch,capture_output=True,timeout=45,startupinfo=startup,creationflags=subprocess.CREATE_NO_WINDOW)
            report=json.loads((scratch/'result.json').read_text('utf8'))
            assert proc.returncode==report['return_code']==0,report
        assert data==path.read_bytes()
        results.append({'file':name,'sha256':hashlib.sha256(data).hexdigest(),'engine_report':report,'process_exit_code':proc.returncode})
        print(name+' imports successfully.',flush=True)
    (P/'checks/import.json').write_text(json.dumps({'mode':'Actual hidden Bambu --info import, no UI or slicing','files':results,'pass':True},indent=2),encoding='utf8')

if __name__=='__main__':main()
