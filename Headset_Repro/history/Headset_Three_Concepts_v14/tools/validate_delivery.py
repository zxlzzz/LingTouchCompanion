import bpy,sys,json,hashlib,zipfile,xml.etree.ElementTree as ET,numpy as np,trimesh
from pathlib import Path
P=Path(__file__).parent.parent;ROOT=P.parent
def geometry_hash(n):
 o=bpy.data.objects[n];vs=np.array([v.co[:] for v in o.data.vertices],dtype=np.float32);fs=[tuple(p.vertices) for p in o.data.polygons];return hashlib.sha256(vs.tobytes()+repr(fs).encode()).hexdigest()
bpy.ops.wm.open_mainfile(filepath=str(ROOT/'Headset_Layout_v12/Headset_Layout_v12.blend'),load_ui=False,use_scripts=False)
names=['Radxa__OFFICIAL_STEP_MESH','CS30__OFFICIAL_STEP_MESH'];baseline={n:geometry_hash(n) for n in names};result={};ns={'m':'http://schemas.microsoft.com/3dmanufacturing/core/2015/02'}
for k in 'ABC':
 d=P/k;bpy.ops.wm.open_mainfile(filepath=str(d/('Concept_'+k+'.blend')),load_ui=False,use_scripts=False);h={n:geometry_hash(n) for n in names};assert h==baseline,(k,'official meshes changed')
 assert bpy.data.collections.get('08_Sport_Glasses_Form') is None
 assert bpy.data.objects.get('Plug__R25') is None
 assert not [o.name for o in bpy.data.objects if o.name.startswith('ROUTE__')]
 assert abs(bpy.data.objects['MOVE__CS30']['pitch_deg']+20)<1e-5
 with zipfile.ZipFile(d/('Concept_'+k+'.3mf')) as z:
  assert z.testzip() is None;root=ET.fromstring(z.read('3D/3dmodel.model'));assert root.get('unit')=='millimeter';objects=root.findall('m:resources/m:object',ns);meshobs=[o for o in objects if o.find('m:mesh',ns) is not None];allnames=[o.get('name') for o in meshobs]
  assert 'CS30_FINISHED_CASE__89p94x30x25' in allnames
  assert not any(n.startswith('REF_') for n in allnames)
  assert len(allnames)==len(set(allnames));assert sum(n.startswith('WIRE__') for n in allnames)==23
  structure=[];spec=json.load(open(d/'specification.json'));stnames={p['name'] for p in spec['parts'] if p['category']=='structure'};bounds=[]
  for o in meshobs:
   m=o.find('m:mesh',ns);vs=np.array([[float(v.get(q)) for q in ['x','y','z']] for v in m.findall('m:vertices/m:vertex',ns)]);fs=np.array([[int(f.get(q)) for q in ['v1','v2','v3']] for f in m.findall('m:triangles/m:triangle',ns)]);assert np.isfinite(vs).all();assert fs.min()>=0 and fs.max()<len(vs);bounds.extend([vs.min(0),vs.max(0)])
   if o.get('name') in stnames:
    tm=trimesh.Trimesh(vs,fs,process=False);assert tm.is_watertight,o.get('name');structure.append(dict(name=o.get('name'),watertight=True))
  size=np.ptp(bounds,axis=0);assert np.allclose(size,spec['assembly_size_mm'],atol=.001)
  result[k]=dict(mesh_objects=len(meshobs),wire_objects=23,official_mesh_hashes=h,official_meshes_unchanged=True,CS30_finished_case_exported=True,old_form_removed=True,pin25_plug_absent=True,default_downward_pitch_deg=20,three_mf_units='millimeter',structure_meshes=structure,three_mf_dimensions_mm=size.tolist())
(P/'delivery_verification.json').write_text(json.dumps(result,indent=2));print('DELIVERY VERIFIED',[(k,v['mesh_objects']) for k,v in result.items()],flush=True)
