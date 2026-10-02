from pathlib import Path
import json
import numpy as np
import trimesh
ROOT=Path(__file__).resolve().parents[1];P=ROOT/'preview_work'
checks={}
for n in ['original','camera','socket','front_tabs','pocket','battery']:
 a=np.load(P/(n+'.npz'));m=trimesh.Trimesh(a['v'],a['f'],process=False)
 checks[n]={'bounds':m.bounds.tolist(),'watertight':bool(m.is_watertight),
            'volume_mm3':float(m.volume),'triangles':len(m.faces)}
 assert m.is_watertight and m.volume>0
source=np.load(ROOT.parent/'Headset_Prop_Stage1_2026-10-02/reference_normal_mesh.npz')
preview=np.load(P/'original.npz')
assert np.array_equal(preview['f'],source['faces'])
assert np.array_equal(preview['v'],source['vertices']+[0,73.53516495,27.587837475])
checks['original_coordinates_and_faces_preserved_exactly']=True
checks['manufacturing_union_generated']=False
checks['fit_or_slice_validation_passed']=False
(ROOT/'audit/preview_geometry_checks.json').write_text(json.dumps(checks,indent=2),encoding='utf8')
print(json.dumps(checks,indent=2))
