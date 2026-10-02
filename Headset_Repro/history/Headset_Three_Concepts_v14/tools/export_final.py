import bpy,sys,json,math,zipfile,xml.etree.ElementTree as ET,numpy as np,trimesh,manifold3d as md
from pathlib import Path
from mathutils import Vector
P=Path(__file__).parent;D=P.parent/sys.argv[1];K=sys.argv[1]
bpy.ops.wm.open_mainfile(filepath=str(D/('Concept_'+K+'.blend')),load_ui=False,use_scripts=False);s=bpy.context.scene;s.frame_set(1);cam=bpy.data.objects['MOVE__CS30'];cam['pitch_deg']=-20;cam.update_tag();bpy.context.view_layer.update();bpy.context.preferences.filepaths.save_version=0
dg=bpy.context.evaluated_depsgraph_get();meshes=[];parts=[];allpoints=[]
for ob in bpy.data.objects:
 if ob.type not in ['MESH','CURVE'] or not ob.get('export_physical'):continue
 eo=ob.evaluated_get(dg);me=eo.to_mesh();me.calc_loop_triangles();v=np.array([eo.matrix_world@q.co for q in me.vertices]);f=np.array([t.vertices[:] for t in me.loop_triangles],int);eo.to_mesh_clear()
 if not len(v):continue
 cat=ob.get('part_category','component');tm=trimesh.Trimesh(v,f,process=False)
 if ob.type=='CURVE':tm.merge_vertices(digits_vertex=7)
 v=np.array(tm.vertices);f=np.array(tm.faces);mat=ob.active_material;color=tuple(mat.diffuse_color) if mat else (.3,.3,.3,1)
 meshes.append((ob.name,v,f,color));allpoints.append(v);item=dict(name=ob.name,category=cat,volume_mm3=abs(float(tm.volume)),dimensions_mm=np.ptp(v,axis=0).tolist(),watertight=bool(tm.is_watertight))
 if cat=='structure':
  so=md.Manifold(md.Mesh(np.ascontiguousarray(v,np.float32),np.ascontiguousarray(f,np.uint32)));item.update(connected_parts=len([p for p in so.decompose() if p.volume()>1]),solid_status=str(so.status()),PETG_g=so.volume()/1000*1.27)
 parts.append(item)
NS='http://schemas.microsoft.com/3dmanufacturing/core/2015/02';ET.register_namespace('',NS)
model=ET.Element('{'+NS+'}model',unit='millimeter');ET.SubElement(model,'metadata',name='Title').text='Concept '+K+' — named assembly, devices / wires / shells';res=ET.SubElement(model,'resources');build=ET.SubElement(model,'build');pal=ET.SubElement(res,'basematerials',id='1')
for i,(name,v,f,col) in enumerate(meshes):ET.SubElement(pal,'base',name=name,displaycolor='#'+''.join(f'{round(max(0,min(1,c))*255):02X}' for c in col))
for idx,(name,v,f,col) in enumerate(meshes,2):
 o=ET.SubElement(res,'object',id=str(idx),type='model',name=name,pid='1',pindex=str(idx-2));m=ET.SubElement(o,'mesh');vs=ET.SubElement(m,'vertices');fs=ET.SubElement(m,'triangles')
 for x,y,z in v:ET.SubElement(vs,'vertex',x=f'{x:.8f}',y=f'{y:.8f}',z=f'{z:.8f}')
 for a,b,c in f:ET.SubElement(fs,'triangle',v1=str(a),v2=str(b),v3=str(c))
rootid=len(meshes)+2;o=ET.SubElement(res,'object',id=str(rootid),type='model',name='Concept_'+K+'_ASSEMBLY');cs=ET.SubElement(o,'components')
for idx in range(2,len(meshes)+2):ET.SubElement(cs,'component',objectid=str(idx))
ET.SubElement(build,'item',objectid=str(rootid))
with zipfile.ZipFile(D/('Concept_'+K+'.3mf'),'w',zipfile.ZIP_DEFLATED) as z:
 z.writestr('[Content_Types].xml','<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>')
 z.writestr('_rels/.rels','<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Target="/3D/3dmodel.model" Id="rel0" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>')
 z.writestr('3D/3dmodel.model',ET.tostring(model,encoding='utf-8',xml_declaration=True))
vv=np.vstack(allpoints);printmass=sum(p.get('PETG_g',0) for p in parts);routes=json.loads((D/'routes.json').read_text());checks=json.loads((D/'checks.json').read_text());wiremass=0;wirelength={}
for n,r in routes.items():
 length=next(x['length_mm'] for x in checks['bend_checks'] if x['name']==n and x['pitch']==20);wirelength[n]=length;wiremass+=length/1000*(12 if r['radius_mm']>1 else 2.2 if 'SPEAKER' in n else 1.2)
heatvol=next(p['volume_mm3'] for p in parts if p['name']=='5519A_copper_block');heatmass=heatvol/1000*8.96
hardware=sum(1 for p in parts if p['name'].startswith('M2__'))*.25+5
mass=dict(camera_g=74,battery_g=143,radxa_estimate_g=11,heatsink_solid_copper_estimate_g=heatmass,header_estimate_g=4,IMU_estimate_g=2,mic_estimate_g=1.5,amp_estimate_g=2,splitter_estimate_g=5,speaker_estimate_g=8,plugs_estimate_g=18,wires_estimate_g=wiremass,PETG_structure_g=printmass,fasteners_estimate_g=hardware,band_pads_sleeves_estimate_g={'A':22,'B':17,'C':26}[K]);total=sum(mass.values());err=printmass*.15+wiremass*.3+20
info=dict(key=K,mesh_objects=len(meshes),assembly_size_mm=np.ptp(vv,axis=0).tolist(),parts=parts,mass_breakdown_g=mass,estimated_total_g=total,estimated_range_g=[total-err,total+err],wire_lengths_mm=wirelength,material_density_g_cm3=1.27,mass_basis='Geometric solid PETG volume × assumed 1.27 g/cm3. Camera 74g and battery 143g from manufacturer; all other items are estimates, not weighed. Approximate range reflects print and unmeasured hardware variation.')
(D/'specification.json').write_text(json.dumps(info,indent=2))
# Render actual CAD geometry, preserving an independently switchable gray reference head in the blend.
s.render.engine='BLENDER_WORKBENCH';s.display.shading.light='STUDIO';s.display.shading.studio_light='paint.sl';s.display.shading.color_type='MATERIAL';s.display.shading.show_shadows=True;s.display.shading.show_cavity=True;s.display.shading.cavity_type='BOTH';s.display.shading.curvature_ridge_factor=1.3;s.display.shading.curvature_valley_factor=1.05;s.display.shading.background_type='WORLD';s.world.color=(.86,.89,.92);s.render.film_transparent=False;s.render.resolution_x=1600;s.render.resolution_y=1300;s.render.resolution_percentage=100
focus=Vector((0,0,28));viewpts=[Vector(q) for q in vv[::max(1,len(vv)//3000)]]
# Include only the head's useful fitting region, without letting the lower neck dominate framing.
viewpts += [Vector((x,y,z)) for x in [-78,78] for y in [-96,96] for z in [-85,116]]
views=[('01_front','VIEW_FRONT',(0,700,30)),('02_right','VIEW_RIGHT',(700,0,30)),('03_top','VIEW_TOP',(0,0,700)),('04_isometric','VIEW_ISO',(450,600,360))]
for label,n,loc in views:
 c=bpy.data.objects[n];c.data.type='ORTHO';c.location=loc;c.rotation_euler=(focus-c.location).to_track_quat('-Z','Y').to_euler();bpy.context.view_layer.update();iv=c.matrix_world.inverted();ps=np.array([iv@q for q in viewpts]);lo=ps.min(0);hi=ps.max(0);middle=(lo+hi)/2;c.location+=c.matrix_world.to_3x3()@Vector((float(middle[0]),float(middle[1]),0));c.data.ortho_scale=float(max(hi[0]-lo[0],(hi[1]-lo[1])*1600/1300)*1.09);s.camera=c;s.render.filepath=str(D/(label+'.png'));bpy.ops.render.render(write_still=True)
s.camera=bpy.data.objects['VIEW_ISO']
for screen in bpy.data.screens:
 for ar in screen.areas:
  if ar.type=='VIEW_3D':ar.spaces.active.region_3d.view_location=focus;ar.spaces.active.region_3d.view_distance=360;ar.spaces.active.region_3d.view_rotation=s.camera.matrix_world.to_quaternion()
scene_props={'CS30_pitch_deg':-20.,'PETG_density_g_cm3':1.27,'nominal_wall_mm':2.,'guide_wall_mm':1.6,'board_slot_clearance_mm':.3,'rear_strap_width_mm':25.,'strap_extension_mm':20.,'reference_head_width_mm':156.}
for k,v in scene_props.items():s[k]=v
for t in list(bpy.data.texts):
 if t.name.startswith('READ_ME_Design'):bpy.data.texts.remove(t)
readme=bpy.data.texts.new('READ_ME_Design');readme.write('Concept '+K+'\nChange MOVE__CS30["pitch_deg"] between -20 and 0. Its IMU carrier and camera cable update together.\n09_Printable_Structure is the load carrier, removable covers and independent battery cradle. 10_Wiring contains editable named Bezier cables. 11_Hardware_and_Soft_Parts contains band, pads and fasteners.\nDimensions and mass: specification.json; actual check evidence: checks.json. Do not slice the complete assembly as one printable object.\nSupply wiring is mechanical provision; the single-input power distribution in glass.md remains electrically unresolved.\n')
bpy.ops.wm.save_as_mainfile(filepath=str(D/'exported.blend'))
import os
os.replace(D/'exported.blend',D/('Concept_'+K+'.blend'))
print('EXPORTED',K,len(meshes),'MASS',round(total),'SIZE',np.ptp(vv,axis=0).round(1),flush=True)
