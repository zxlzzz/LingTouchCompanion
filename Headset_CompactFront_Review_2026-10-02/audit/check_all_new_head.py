from pathlib import Path
import ast,json,sys,hashlib
import numpy as np
P=Path(__file__).resolve().parent;ROOT=P.parents[1];G=P.parent/'geometry';R=ROOT/'Headset_Carbon6K_FlatBase_Review_2026-10-02'
source=R/'audit/audit_surface_distances.py';tree=ast.parse(source.read_text(encoding='utf8'));nodes=[a for a in tree.body if isinstance(a,(ast.Import,ast.ImportFrom,ast.FunctionDef)) and not(isinstance(a,ast.FunctionDef) and a.name=='main')]
sys.path.insert(0,str(R/'inputs'));ns={};exec(compile(ast.Module(nodes,type_ignores=[]),str(source),'exec'),ns)
a=np.load(R/'inputs/Medium_Trial_Registered.npz');HV,HF=a['v'],a['f'];H=HV[HF]
b=np.load(G/'added_material.npz');V,F=b['v'],b['f'];C=V[F]
# Full head, all new material; no Y<0 restriction for this revision.
report={'new_material_head':ns['continuous_min'](HV,HF,V,F),'source_sha256':hashlib.sha256((G/'front_unified_preview.npz').read_bytes()).hexdigest()}
keep=(np.abs(H[:,:,0]).max(1)<30)&(H[:,:,1].min(1)<12)&(H[:,:,2].max(1)>-10)&(H[:,:,2].min(1)<45)
N=H[keep];lo,hi=N.min((0,1)),N.max((0,1));gap=np.maximum(np.maximum(lo-C.max(1),C.min(1)-hi),0);from scipy.spatial import cKDTree; ub=float(cKDTree(N.reshape(-1,3)).query(V)[0].min()); C=C[(gap*gap).sum(1)<=(ub+1e-8)**2]
tabs=np.load(G/'tabs_added.npz'); report['retained_ear_head']=ns['continuous_min'](HV,HF,tabs['v'],tabs['f'])
report['new_material_nose_all_Y']=ns['continuous_min'](N.reshape(-1,3),np.arange(N.size//3).reshape(-1,3),C.reshape(-1,3),np.arange(C.size//3).reshape(-1,3))
(P/'new_head_clearance.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report,indent=2))



