"""Index saved checks and identify their referenced geometry revisions."""
from pathlib import Path
import hashlib, json

REPO = Path(__file__).resolve().parent.parent
DIRS = [REPO/'Headset_CompactFront_Review_2026-10-02',
        REPO/'Headset_Carbon6K_FlatBase_Review_2026-10-02']

def main():
    meshes = {}
    for directory in DIRS:
        for source in directory.rglob('*.npz'):
            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            meshes.setdefault(digest, []).append(source.relative_to(REPO).as_posix())
    def hashes(value, trail=''):
        rows = []
        if isinstance(value, dict):
            for key, val in value.items():
                path = trail+'/'+key
                if isinstance(val, str) and 'sha256' in key and len(val)==64:
                    rows.append({'field':path, 'sha256':val,
                                 'matching_packaged_meshes':meshes.get(val, []),
                                 'status':'packaged mesh present' if val in meshes else 'not a current packaged NPZ hash; inspect scope/version'})
                else:
                    rows.extend(hashes(val,path))
        elif isinstance(value,list):
            for i,val in enumerate(value):
                rows.extend(hashes(val,trail+'/'+str(i)))
        return rows
    rows=[]
    for directory in DIRS:
        for source in sorted((directory/'audit').glob('*.json')):
            data=json.loads(source.read_text(encoding='utf-8-sig'))
            rows.append({'result':source.relative_to(REPO).as_posix(),
                         'referenced_hashes':hashes(data)})
    out=REPO/'Headset_Repro/verification/check_results_index.json'
    out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps({'note':'Saved check results are retained as evidence. A present hash identifies a mesh, not a successful check; unmatched hashes must not be taken as verification of the latest shell.',
                               'results':rows},indent=2),encoding='utf8')
    print('Indexed',len(rows),'saved check results')

if __name__=='__main__':
    main()
