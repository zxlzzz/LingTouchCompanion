"""Regenerate the unchanged registered head from the original scale-1 STL."""
from pathlib import Path
import json
import numpy as np
import trimesh

P=Path(__file__).resolve().parent
def main():
    datums=json.loads((P/'datums.json').read_text('utf8'))
    m=trimesh.load(P/'Medium_Symmetry.stl',process=True)
    t=np.array(datums['head_native_to_wearing'])
    v=np.asarray(m.vertices)@t[:3,:3].T+t[:3,3]
    f=np.asarray(m.faces)
    target=P/'Medium_Trial_Registered.npz'
    if target.exists():
        old=np.load(target)
        assert old['v'].shape==v.shape and old['f'].shape==f.shape
        assert np.max(np.abs(old['v']-v))<1e-9
        assert np.array_equal(old['f'],f)
    np.savez_compressed(target,v=v,f=f)
    print('Registered head regenerated from original STL:',len(v),len(f))
if __name__=='__main__':main()
