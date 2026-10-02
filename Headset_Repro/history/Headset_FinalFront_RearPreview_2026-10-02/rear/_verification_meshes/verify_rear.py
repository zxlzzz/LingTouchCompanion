from pathlib import Path
import hashlib,json,zipfile,xml.etree.ElementTree as ET
import numpy as np
import trimesh
import manifold3d as md

HERE=Path(__file__).resolve().parent.parent
APPROVED=HERE.parent/'rear_work'
AUDIT=HERE/'_verification_meshes'
M=md.Manifold
def h(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def npzm(p):
 a=np.load(p);return M(md.Mesh64(vert_properties=np.ascontiguousarray(a['v'],dtype=np.float64),tri_verts=np.ascontiguousarray(a['f'],dtype=np.uint64)))
def diff(a,b):
 ab=a-b;ba=b-a
 assert ab.status()==md.Error.NoError and ba.status()==md.Error.NoError
 return {'generated_minus_approved_mm3':abs(float(ab.volume())),'approved_minus_generated_mm3':abs(float(ba.volume())),'symmetric_difference_mm3':abs(float(ab.volume()))+abs(float(ba.volume()))}

values=json.loads((HERE/'rear_geometry_values.json').read_text())
report={'verification_method':'Read package XML back, validate closed connected solid, invert baked placement, and compare physical solids with approved preview. Ordered mesh arrays are not the geometry criterion.','approved_preview_sha256':h(APPROVED/'rear_unified_preview.npz'),'final_3mf_sha256':h(HERE/'Rear_Final.3mf'),'generator_sha256':h(HERE/'generate_rear.py')}
approved=npzm(APPROVED/'rear_unified_preview.npz')
generated=npzm(AUDIT/'rear_unified.npz')
report['generated_vs_approved']=diff(generated,approved)
report['procedural_box_vs_approved']=diff(npzm(AUDIT/'rear_box.npz'),npzm(APPROVED/'rear_box.npz'))
with zipfile.ZipFile(HERE/'Rear_Final.3mf') as z:
 root=ET.fromstring(z.read('3D/3dmodel.model'))
 ns={'m':'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'}
 objects=root.findall('m:resources/m:object',ns);items=root.findall('m:build/m:item',ns)
 obj=objects[0]
 v=np.array([[float(n.attrib[x]) for x in ['x','y','z']] for n in obj.findall('m:mesh/m:vertices/m:vertex',ns)])
 f=np.array([[int(n.attrib[x]) for x in ['v1','v2','v3']] for n in obj.findall('m:mesh/m:triangles/m:triangle',ns)],dtype=np.uint64)
 tm=trimesh.Trimesh(v,f,process=False)
 packed=M(md.Mesh64(vert_properties=np.ascontiguousarray(v,dtype=np.float64),tri_verts=np.ascontiguousarray(f,dtype=np.uint64)))
 report['readback']={'units':root.attrib.get('unit'),'object_count':len(objects),'build_item_count':len(items),'vertices':len(v),'triangles':len(f),'bounds_xyz_mm':[v.min(0).tolist(),v.max(0).tolist()],'dimensions_xyz_mm':np.ptp(v,axis=0).tolist(),'watertight':bool(tm.is_watertight),'winding_consistent':bool(tm.is_winding_consistent),'manifold_status':str(packed.status()),'connected_closed_solids':len(packed.decompose()),'volume_mm3':float(packed.volume())}
 shift=np.array(values['print_placement']['translation_xyz_mm']);worldv=v-shift
 world=M(md.Mesh64(vert_properties=np.ascontiguousarray(worldv,dtype=np.float64),tri_verts=np.ascontiguousarray(f,dtype=np.uint64)))
 report['readback_inverse_placement_vs_approved']=diff(world,approved)
 assert report['readback']['units']=='millimeter'
 assert len(objects)==len(items)==1
 assert tm.is_watertight and tm.is_winding_consistent
 assert packed.status()==md.Error.NoError and len(packed.decompose())==1
 assert np.allclose(v.min(0),0,atol=1e-12)
 assert np.allclose(np.ptp(v,axis=0),[136.6,43.55839557297662,47],atol=1e-10)
 for key in ['generated_vs_approved','procedural_box_vs_approved','readback_inverse_placement_vs_approved']:
  assert report[key]['symmetric_difference_mm3']<1e-5,(key,report[key])
 report['all_checks_passed']=True
 report['comparison_tolerance_mm3']=1e-5
 report['physical_fit_insertion_strength_and_slicing']='Not checked'
(HERE/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report,indent=2))
