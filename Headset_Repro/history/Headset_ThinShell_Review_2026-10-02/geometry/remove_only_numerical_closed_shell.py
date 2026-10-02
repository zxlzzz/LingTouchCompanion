"""Remove zero-volume numerical components while retaining real voids."""
from pathlib import Path
import json
import numpy as np
import manifold3d as md
P=Path(__file__).resolve().parent;M=md.Manifold
a=np.load(P/'front_unified_preview.npz')
m=M(md.Mesh64(vert_properties=np.ascontiguousarray(a['v'],dtype=np.float64),tri_verts=np.ascontiguousarray(a['f'],dtype=np.uint64)))
parts=m.decompose();outer=[q for q in parts if q.volume()>1e-5];cavities=[q for q in parts if q.volume()<-1e-5]
assert len(outer)==1
air=[]
for q in cavities:
 me=q.to_mesh64();air.append(M(md.Mesh64(vert_properties=np.ascontiguousarray(np.array(me.vert_properties)[:,:3],dtype=np.float64),tri_verts=np.ascontiguousarray(np.array(me.tri_verts)[:,::-1],dtype=np.uint64))))
clean=outer[0]-M.batch_boolean(air,md.OpType.Add)
assert clean.status()==md.Error.NoError
me=clean.to_mesh64();v=np.array(me.vert_properties)[:,:3];f=np.array(me.tri_verts)
np.savez_compressed(P/'front_unified_preview.npz',v=v,f=f)
info=json.loads((P/'geometry_values.json').read_text())
info['front_unified_preview']={'vertices':len(v),'triangles':len(f),'bounds_xyz_mm':[v.min(0).tolist(),v.max(0).tolist()],'volume_mm3':float(clean.volume()),'components':len(clean.decompose()),'status':str(clean.status())}
info['volume_cm3']=float(clean.volume())/1000
info['numerical_zero_air_shell_removed_volume_mm3']=sum(abs(float(q.volume())) for q in parts if abs(q.volume())<=1e-5)
(P/'geometry_values.json').write_text(json.dumps(info,indent=2),encoding='utf8')
print(json.dumps(info['front_unified_preview'],indent=2))
