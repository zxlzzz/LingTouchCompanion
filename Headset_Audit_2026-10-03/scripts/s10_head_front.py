"""Step 10: front part vs the head model (Medium headform, as registered in the delivered 3MF).
new material = delivered shell minus original BTTF (own boolean)."""
import json, numpy as np
import manifold3d as md
import trimesh
from common import read_3mf, FRONT_3MF, DATA
from headdist import Head, report
M = md.Manifold
objs = read_3mf(FRONT_3MF)
SV, SF = objs['Front_Compact_Review_shell']; HV, HF = objs['Head_reference_do_not_print']
CV, CF = objs['Front_Compact_Review_occupant_reference_do_not_print']
b = np.load(DATA / 'bttf_normal_wearing.npz')
man = lambda V, F: M(md.Mesh64(vert_properties=np.ascontiguousarray(V, float), tri_verts=np.ascontiguousarray(F, np.uint64)))
shell = man(SV, SF); bttf = man(b['v'], b['f'])
new = shell - bttf
parts = [p for p in new.decompose() if p.volume() > 0.5]
newm = M.batch_boolean(parts, md.OpType.Add)
nm = newm.to_mesh64(); NV = np.array(nm.vert_properties)[:, :3]; NF = np.array(nm.tri_verts, np.int64)
np.savez_compressed(DATA / 'front_new_material.npz', v=NV, f=NF)
removed = bttf - shell
head = Head(HV, HF, crop_lo=SV.min(0) - 15, crop_hi=SV.max(0) + 15)
def samples(V, F, n):
    P, _ = trimesh.sample.sample_surface(trimesh.Trimesh(V, F, process=False), n, seed=3); return np.vstack([P, V])
res = {'new_material_volume_cm3': newm.volume() / 1000, 'new_material_pieces_over_0.5mm3': len(parts),
       'tiny_pieces_dropped_mm3': float(new.volume() - newm.volume()),
       'original_removed_volume_cm3': removed.volume() / 1000, 'shell_volume_cm3': shell.volume() / 1000}
res['camera_box_to_head'] = report(head, samples(CV, CF, 200000))
Pn = samples(NV, NF, 400000)
r = report(head, Pn); ins = r.pop('_inside_mask', None); res['new_material_to_head'] = r
if ins is not None:
    np.save(DATA / 'new_material_inside_head_pts.npy', Pn[ins])
nose = (np.abs(Pn[:, 0]) < 30) & (Pn[:, 2] < 45) & (Pn[:, 1] < 30)
r = report(head, Pn[nose], inside=False); res['new_material_to_head_nose_zone(|X|<30,Z<45,Y<30)'] = r
Ps = samples(SV, SF, 600000)
r = report(head, Ps); ins = r.pop('_inside_mask', None); res['whole_shell_to_head'] = r
if ins is not None:
    np.save(DATA / 'shell_inside_head_pts.npy', Ps[ins])
json.dump(res, open(DATA / 'head_front.json', 'w'), indent=1)
print(json.dumps(res, indent=1))
