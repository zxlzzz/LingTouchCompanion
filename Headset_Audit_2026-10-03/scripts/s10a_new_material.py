"""Step 10a: new material of the front part = delivered shell minus the original BTTF (own boolean)."""
import json, time, numpy as np
import manifold3d as md
from common import read_3mf, FRONT_3MF, DATA
M = md.Manifold
t0 = time.time()
SV, SF = read_3mf(FRONT_3MF)['Front_Compact_Review_shell']
b = np.load(DATA / 'bttf_normal_wearing.npz')
man = lambda V, F: M(md.Mesh64(vert_properties=np.ascontiguousarray(V, float), tri_verts=np.ascontiguousarray(F, np.uint64)))
shell = man(SV, SF); bttf = man(b['v'], b['f'])
print('loaded', time.time() - t0, flush=True)
new = shell - bttf
print('boolean', time.time() - t0, flush=True)
parts = new.decompose()
vols = sorted([p.volume() for p in parts], reverse=True)
keep = [p for p in parts if p.volume() > 0.5]
newm = M.batch_boolean(keep, md.OpType.Add)
nm = newm.to_mesh64(); NV = np.array(nm.vert_properties)[:, :3]; NF = np.array(nm.tri_verts, np.int64)
np.savez_compressed(DATA / 'front_new_material.npz', v=NV, f=NF)
removed = bttf - shell
res = {'shell_cm3': shell.volume() / 1000, 'bttf_cm3': bttf.volume() / 1000, 'new_material_cm3': newm.volume() / 1000,
       'new_pieces_over_0.5mm3': len(keep), 'new_piece_volumes_mm3_top': [round(v, 2) for v in vols[:12]],
       'tiny_pieces_total_mm3': float(sum(v for v in vols if v <= 0.5)), 'original_removed_cm3': removed.volume() / 1000}
json.dump(res, open(DATA / 'front_new_material.json', 'w'), indent=1); print(json.dumps(res, indent=1), time.time() - t0)
