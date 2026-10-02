from pathlib import Path
import json,hashlib
import numpy as np,manifold3d as md
P=Path(__file__).resolve().parent;G=P.parent/'geometry';M=md.Manifold
def load(n):
 a=np.load(G/(n+'.npz'));return M(md.Mesh64(vert_properties=a['v'],tri_verts=a['f'].astype(np.uint64)))
shape=load('added_material')-load('hooks')-load('tabs_added')
eroded=shape.minkowski_difference(M.sphere(1.5,circular_segments=8))
result={'source_sha256':hashlib.sha256((G/'front_unified_preview.npz').read_bytes()).hexdigest(),'metric':'Conservative maximum inscribed-ball diameter3mm test; not a universal normal-thickness map. Original BTTF and retained old ears excluded; new raised rim included.','eroded_empty':eroded.is_empty(),'eroded_volume_mm3':eroded.volume(),'eroded_bounds':None if eroded.is_empty() else list(eroded.bounding_box())}
if not eroded.is_empty():
 a=eroded.to_mesh64();np.savez_compressed(G/'thickness_witness.npz',v=np.array(a.vert_properties)[:,:3],f=np.array(a.tri_verts))
(P/'new_thickness.json').write_text(json.dumps(result,indent=2),encoding='utf8');print(json.dumps(result,indent=2))


