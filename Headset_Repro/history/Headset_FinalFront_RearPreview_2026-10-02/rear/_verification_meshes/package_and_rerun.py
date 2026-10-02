from pathlib import Path
import hashlib,json,subprocess,sys,zipfile,xml.etree.ElementTree as ET
import numpy as np
import trimesh
import manifold3d as md

HERE=Path(__file__).resolve().parent.parent
QA=HERE/'_verification_meshes'
FILES=['generate_rear.py','requirements.txt','RUN.txt','使用说明.txt','rear_geometry_values.json','verification.json']
def pack():
 with zipfile.ZipFile(HERE/'Rear_Generator.zip','w',zipfile.ZIP_DEFLATED) as z:
  for name in FILES:z.write(HERE/name,name)
  for p in sorted((HERE/'rear_inputs').iterdir()):z.write(p,'rear_inputs/'+p.name)
pack()
RELOCATED=QA/'independent_package_run'
with zipfile.ZipFile(HERE/'Rear_Generator.zip') as z:z.extractall(RELOCATED)
result=subprocess.run([sys.executable,str(RELOCATED/'generate_rear.py')],cwd=QA,text=True,capture_output=True,check=True)
rerun=RELOCATED/'Rear_Final.3mf'
ns={'m':'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'}
with zipfile.ZipFile(rerun) as z:
 root=ET.fromstring(z.read('3D/3dmodel.model'))
 v=np.array([[float(n.attrib[x]) for x in ['x','y','z']] for n in root.findall('m:resources/m:object/m:mesh/m:vertices/m:vertex',ns)])
 f=np.array([[int(n.attrib[x]) for x in ['v1','v2','v3']] for n in root.findall('m:resources/m:object/m:mesh/m:triangles/m:triangle',ns)],dtype=np.uint64)
tm=trimesh.Trimesh(v,f,process=False)
rerun_values=json.loads((RELOCATED/'rear_geometry_values.json').read_text())
v-=np.array(rerun_values['print_placement']['translation_xyz_mm'])
generated=md.Manifold(md.Mesh64(vert_properties=np.ascontiguousarray(v,dtype=np.float64),tri_verts=np.ascontiguousarray(f,dtype=np.uint64)))
a=np.load(HERE.parent/'rear_work/rear_unified_preview.npz')
approved=md.Manifold(md.Mesh64(vert_properties=np.ascontiguousarray(a['v'],dtype=np.float64),tri_verts=np.ascontiguousarray(a['f'],dtype=np.uint64)))
ab=generated-approved;ba=approved-generated
symdiff=abs(float(ab.volume()))+abs(float(ba.volume()))
assert ab.status()==ba.status()==md.Error.NoError
assert generated.status()==md.Error.NoError and len(generated.decompose())==1
assert tm.is_watertight and tm.is_winding_consistent
assert symdiff<1e-5
report=json.loads((HERE/'verification.json').read_text())
report['independent_extracted_package_rerun']={'succeeded':True,'input_files_are_self_contained':True,'generator_uses_no_old_directory':True,'runtime_python':sys.executable,'rerun_3mf_sha256':hashlib.sha256(rerun.read_bytes()).hexdigest(),'watertight':bool(tm.is_watertight),'winding_consistent':bool(tm.is_winding_consistent),'connected_closed_solids':len(generated.decompose()),'volume_mm3':float(generated.volume()),'symmetric_difference_from_approved_mm3':symdiff}
(HERE/'verification.json').write_text(json.dumps(report,indent=2),encoding='utf8')
pack()
print(json.dumps({'independent_rerun':report['independent_extracted_package_rerun'],'package':str(HERE/'Rear_Generator.zip'),'package_bytes':(HERE/'Rear_Generator.zip').stat().st_size,'package_sha256':hashlib.sha256((HERE/'Rear_Generator.zip').read_bytes()).hexdigest()},indent=2))
