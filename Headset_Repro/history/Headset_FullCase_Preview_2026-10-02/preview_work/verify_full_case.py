from pathlib import Path
import json
import numpy as np
import trimesh, manifold3d as md
ROOT=Path(__file__).resolve().parents[1];W=ROOT/'preview_work';meshes={};solid={};out={}
for n in ['original_reference','original_modified','case_material','case_envelope','front_unified_preview','front_tabs','camera','pocket']:
 a=np.load(W/(n+'.npz'));m=trimesh.Trimesh(a['v'],a['f'],process=False);meshes[n]=m
 s=md.Manifold(md.Mesh64(vert_properties=np.ascontiguousarray(m.vertices),tri_verts=np.ascontiguousarray(m.faces,dtype=np.uint64)));solid[n]=s
 assert m.is_watertight and m.volume>0 and s.status()==md.Error.NoError
 out[n]={'bounds':m.bounds.tolist(),'volume_mm3':float(m.volume),'triangles':len(m.faces),'watertight':True,'components':len(s.decompose())}
outside=solid['camera']-solid['case_envelope']
interference=solid['camera']^solid['front_unified_preview']
out['camera_volume_outside_outer_envelope_mm3']=outside.volume()
out['camera_solid_interference_with_printed_geometry_mm3']=interference.volume()
print('Camera outside:',outside.volume(),outside.num_tri(),outside.bounding_box())
print('Camera interference:',interference.volume(),interference.num_tri(),interference.bounding_box())
assert abs(outside.volume())<1e-8 and abs(interference.volume())<1e-8
a=np.load(W/'original_reference.npz');source=np.load(ROOT.parent/'Headset_Prop_Stage1_2026-10-02/reference_normal_mesh.npz')
assert np.array_equal(a['f'],source['faces']) and np.array_equal(a['v'],source['vertices']+[0,73.53516495,27.587837475])
out['original_reference_unchanged_exactly']=True
out['face_recess_nominal_mm']=0
out['front_single_connected_solid']=len(solid['front_unified_preview'].decompose())==1
out['printing_fit_elasticity_slice_checked']=False
(ROOT/'audit/preview_mesh_checks.json').write_text(json.dumps(out,indent=2),encoding='utf8')
print(json.dumps(out,indent=2))
