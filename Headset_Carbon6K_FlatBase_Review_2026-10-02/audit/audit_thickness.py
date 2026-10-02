"""Conservative inscribed-ball bound for the box and strap-plate assembly."""
from pathlib import Path
import hashlib,json
import numpy as np
import manifold3d as md
P=Path(__file__).resolve().parent; G=P.parent/'geometry'
def load(name):
 a=np.load(G/(name+'.npz'))
 return md.Manifold(md.Mesh64(vert_properties=np.ascontiguousarray(a['v'],dtype=np.float64),tri_verts=np.ascontiguousarray(a['f'],dtype=np.uint64)))
shape=md.Manifold.batch_boolean([load(n) for n in ['rear_box','rear_left_strap_plate','rear_right_strap_plate']],md.OpType.Add)
eroded=shape.minkowski_difference(md.Manifold.sphere(1.5,circular_segments=16))
result={'rear_source_sha256':hashlib.sha256((G/'rear_unified_preview.npz').read_bytes()).hexdigest(),
 'scope':'box+rear clip+two strap plates; curved tray and joining ribs excluded',
 'method':'Morphological erosion by an inscribed radius1.5 sphere polyhedron. Empty erosion conservatively excludes any larger diameter3 inscribed ball; this is not a global normal-thickness measurement.',
 'eroded_empty':eroded.is_empty(),'volume_mm3':eroded.volume(),
 'maximum_inscribed_ball_diameter_bound_mm':3 if eroded.is_empty() else None}
(P/'box_plate_thickness.json').write_text(json.dumps(result,indent=2),encoding='utf8')
print(json.dumps(result,indent=2))
