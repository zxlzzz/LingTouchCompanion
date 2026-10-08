"""Add the retained handle meshes to the interactive array, without editing inputs.

The 3MF meshes were centred separately on import. Source-offset metadata recovers
their original STEP coordinate frames; printing orientations are not used as an
assembly pose. The complete array receives one vertical translation only.
"""
from pathlib import Path
import hashlib,json,sys,math
import xml.etree.ElementTree as ET
import numpy as np
import bpy,bmesh
from mathutils import Vector

P=Path(__file__).resolve().parent
ROOT=P.parents[1]
sys.path.insert(0,str(ROOT/'3mf/Handle'))
from source import SOURCE,read_source

TOUCH_CENTRE_X=64.0
CAD_Y_TO_HEIGHT=31.0
ARRAY_LIFT=30.7
SWITCH_HEIGHT=20.0
SWITCH_NOSE_HEIGHT=2.6
SWITCH_HEAD_DIAMETER=4.2
SWITCH_PROTRUSION=1.2
SWITCH_MOUNT_HEIGHT=ARRAY_LIFT+3.8+SWITCH_PROTRUSION
FACEPLATE_OUTER_HEIGHT=54.5

def add_tactile_switch(scene):
    """Use the user's 20 mm total height and the array's module-base datum.

    SW1 in the user's BOM is Khon TSA06131-250B532CA / C49174365.
    Its drawing supplies the 6.1 mm footprint and 3.2 mm stem. The user now
    requests a smooth bullet-shaped head rather than the photographed flutes.
    The user's explicit 20 mm height takes precedence over the BOM's 25 mm.
    """
    collection=bpy.data.collections.new('TACTILE SWITCH - visual assembly')
    scene.collection.children.link(collection)
    materials={}
    for name,colour,roughness,metal in [
        ('plastic',(.006,.0065,.007,1),.38,0),
        ('steel',(.48,.49,.50,1),.32,.90),
    ]:
        mat=bpy.data.materials.new('Web switch '+name);mat.use_nodes=True;mat.diffuse_color=colour
        shader=mat.node_tree.nodes.get('Principled BSDF');shader.inputs['Base Color'].default_value=colour
        shader.inputs['Roughness'].default_value=roughness;shader.inputs['Metallic'].default_value=metal
        materials[name]=mat
    cx,cy=0.,44.5-TOUCH_CENTRE_X
    objects=[]
    def finish_object(obj,name,kind,bevel=0):
        obj.name='Switch_'+name
        for old in list(obj.users_collection):old.objects.unlink(obj)
        collection.objects.link(obj);obj.data.materials.append(materials[kind]);obj['switch_part']=kind
        obj['role']='BOM-referenced Khon switch, user-requested 20 mm visual variant; no electrical connection'
        if bevel:
            mod=obj.modifiers.new('Small moulded edge radius','BEVEL');mod.width=bevel*.001;mod.segments=3
            mod=obj.modifiers.new('Weighted face normals','WEIGHTED_NORMAL');mod.keep_sharp=True
        objects.append(obj);return obj
    def box(name,size,centre,kind,bevel=.08):
        bpy.ops.mesh.primitive_cube_add(size=1,location=Vector(centre)*.001)
        obj=bpy.context.object;obj.dimensions=Vector(size)*.001
        bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
        return finish_object(obj,name,kind,bevel)
    def cylinder(name,radius,depth,centre,kind,bevel=.04):
        bpy.ops.mesh.primitive_cylinder_add(vertices=80,radius=radius*.001,depth=depth*.001,
                                          location=Vector(centre)*.001)
        obj=finish_object(bpy.context.object,name,kind,bevel)
        for poly in obj.data.polygons:poly.use_smooth=abs(poly.normal.z)<.5
        return obj
    mount=SWITCH_MOUNT_HEIGHT
    tip=mount+SWITCH_HEIGHT
    assert abs(tip-FACEPLATE_OUTER_HEIGHT-SWITCH_PROTRUSION)<1e-6
    box('Moulded_base_6p1x6p1',(6.1,6.1,3.25),(cx,cy,mount+1.625),'plastic',.09)
    lid=box('Stamped_lid',(6.06,6.06,.25),(cx,cy,mount+3.375),'steel',0)
    bpy.ops.mesh.primitive_cylinder_add(vertices=96,radius=1.84*.001,depth=1*.001,
                                      location=(cx*.001,cy*.001,(mount+3.375)*.001))
    cutter=bpy.context.object
    bpy.context.view_layer.objects.active=lid
    mod=lid.modifiers.new('Actuator clearance through stamped steel','BOOLEAN')
    mod.operation='DIFFERENCE';mod.object=cutter
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(cutter,do_unlink=True)
    mod=lid.modifiers.new('Stamped edge radius','BEVEL');mod.width=.025*.001;mod.segments=3
    mod=lid.modifiers.new('Flat steel normals','WEIGHTED_NORMAL');mod.keep_sharp=True
    # A flared neck joins the wider elliptical bullet nose. The original
    # 3.2 mm shaft passes through the switch lid; the head is 4.2 mm wide.
    # Total height stays 20 mm, with no flat end face.
    nose_radius=SWITCH_HEAD_DIAMETER/2
    nose_base=SWITCH_HEIGHT-SWITCH_NOSE_HEIGHT
    local_profile=[(0,3.40),(2.03,3.40),(2.07,3.44),(2.07,3.68),
                   (2.02,3.73),(1.64,3.73),(1.62,3.79),(1.61,3.95),
                   (1.60,4.25),(1.60,nose_base-.65)]
    for j in range(1,17):
        t=j/16
        local_profile.append((1.6+(nose_radius-1.6)*(3*t*t-2*t*t*t),nose_base-.65+.65*t))
    for j in range(1,64):
        angle=(math.pi/2)*j/64
        local_profile.append((nose_radius*math.cos(angle),
                              SWITCH_HEIGHT-SWITCH_NOSE_HEIGHT+SWITCH_NOSE_HEIGHT*math.sin(angle)))
    local_profile.append((0,SWITCH_HEIGHT))
    profile=[(radius,mount+height) for radius,height in local_profile]
    actuator_origin=mount+3.40
    rings=[];verts=[];faces=[];segments=256
    for radius,height in profile:
        if radius==0:
            rings.append([len(verts)]);verts.append((0,0,(height-actuator_origin)*.001))
        else:
            ring=[]
            for i in range(segments):
                a=2*math.pi*i/segments
                ring.append(len(verts));verts.append((radius*math.cos(a)*.001,radius*math.sin(a)*.001,(height-actuator_origin)*.001))
            rings.append(ring)
    for a,b in zip(rings,rings[1:]):
        for i in range(segments):
            j=(i+1)%segments
            if len(a)==1:faces.append((a[0],b[j],b[i]))
            elif len(b)==1:faces.append((a[i],a[j],b[0]))
            else:faces.append((a[i],a[j],b[j],b[i]))
    mesh=bpy.data.meshes.new('Smooth rounded bullet actuator profile');mesh.from_pydata(verts,[],faces);mesh.update()
    bm=bmesh.new();bm.from_mesh(mesh);bmesh.ops.recalc_face_normals(bm,faces=bm.faces);bm.to_mesh(mesh);bm.free()
    mesh.set_sharp_from_angle(angle=math.radians(35))
    for poly in mesh.polygons:poly.use_smooth=poly.index>=segments
    actuator=bpy.data.objects.new('Moulded bullet actuator',mesh);scene.collection.objects.link(actuator)
    actuator.location=(cx*.001,cy*.001,actuator_origin*.001)
    finish_object(actuator,'Bullet_actuator_20mm','plastic')
    # Four heat-staked plastic posts retain the real thin metal cap.
    for side in [-1,1]:
        for row in [-1,1]:
            cylinder(f'Lid_retainer_{side}_{row}',.43,.16,(cx+side*2.30,cy+row*2.30,mount+3.52),'plastic',.045)
    for side in [-1,1]:
        for row in [-1,1]:
            # Continuous cranked through-hole terminals, not surface-mount feet.
            path=[(3.05,mount+1.60),(3.17,mount+.25),(3.77,mount-1.02),(3.25,mount-2.10),(3.25,mount-3.00)]
            leg_verts=[];leg_faces=[]
            for lateral,height in path:
                for dx,dy in [(-.15,-.35),(.15,-.35),(.15,.35),(-.15,.35)]:
                    leg_verts.append(((side*lateral+dx)*.001,(cy+row*2.25+dy)*.001,height*.001))
            leg_faces.append((0,3,2,1))
            for j in range(len(path)-1):
                for i in range(4):leg_faces.append((4*j+i,4*j+(i+1)%4,4*(j+1)+(i+1)%4,4*(j+1)+i))
            k=4*(len(path)-1);leg_faces.append((k,k+1,k+2,k+3))
            leg_mesh=bpy.data.meshes.new('Bent through-hole terminal');leg_mesh.from_pydata(leg_verts,[],leg_faces);leg_mesh.update()
            bm=bmesh.new();bm.from_mesh(leg_mesh);bmesh.ops.recalc_face_normals(bm,faces=bm.faces);bm.to_mesh(leg_mesh);bm.free()
            leg=bpy.data.objects.new('Long switch terminal',leg_mesh);scene.collection.objects.link(leg)
            finish_object(leg,f'TH_terminal_{side}_{row}','steel',.025)
    bpy.context.view_layer.update()
    actual_tip=max((actuator.matrix_world @ v.co).z for v in actuator.data.vertices)*1000
    actual_bottom=mount
    assert abs(actual_tip-actual_bottom-SWITCH_HEIGHT)<1e-5
    return objects,{
        'kind':'User-requested bullet-head tactile switch, 6.1 x 6.1 x 20 mm visual variant',
        'bom_source':'C:/Users/Hsinlung/Downloads/BOM_Board1_PCB1_5_2026-09-15.xlsx',
        'bom_cells':'bom模板!D44, G44, H44, I44',
        'bom_mpn':'TSA06131-250B532CA','bom_lcsc_part':'C49174365','bom_height_mm':25,
        'height_authority':'User: here the tactile switch is 20 mm high; height excludes PCB legs',
        'photographic_reference':'https://www.lcsc.com/product-image/C49174365.html?whichImg=0',
        'dimension_drawing':'https://datasheet.lcsc.com/datasheet/pdf/1afe2ca538b7779b1f715764ab402911.pdf?productCode=C49174365',
        'drawing_page':9,'retained_reference_pdf':'../inputs/Khon_TSA06131_Reference.pdf',
        'visual_dimensions_only':True,'body_footprint_mm':[6.1,6.1],
        'height_from_virtual_mounting_plane_mm':SWITCH_HEIGHT,'measured_height_from_mesh_mm':actual_tip-actual_bottom,
        'mounting_plane_height_mm':mount,
        'mounting_datum':'Visual switch plane raised 1.2 mm above the module-base plane at user request so the head protrudes above the cover; physical PCB datum is not independently measured',
        'switch_body_height_mm':3.5,'shaft_above_body_mm':16.5,'leg_projection_below_mounting_plane_mm':3.,
        'hole_centre_cad_xz_mm':[44.5,0],'existing_hole_diameter_mm':5,
        'actuator_diameter_mm':3.2,'actuator_top_height_mm':actual_tip,
        'head_authority':'User requested a bullet-shaped head; replaces the rejected fluted flat head',
        'actuator_head_height_mm':SWITCH_NOSE_HEIGHT,
        'actuator_head_diameter_mm':SWITCH_HEAD_DIAMETER,
        'actuator_head_profile':'Smooth elliptical bullet nose, radial semi-axis 2.1 mm, axial semi-axis 2.6 mm; rounded pole and 0.65 mm flared neck from the 3.2 mm shaft',
        'exposed_height_above_faceplate_mm':actual_tip-FACEPLATE_OUTER_HEIGHT,
        'minimum_radial_hole_clearance_mm':(5-SWITCH_HEAD_DIAMETER)/2,
        'metal_lid_thickness_mm':.25,'metal_lid_top_height_mm':mount+3.5,'faceplate_inner_height_mm':52.5,
        'metal_lid_clearance_below_faceplate_mm':52.5-mount-3.5,
        'visible_finish':'Black plastic smooth shaft with a rounded bullet nose and broad environment reflections',
        'interaction':'Static visual switch; does not control the tactile array or BLE.',
    }

def original_offsets(row,metadata):
    part=metadata.find(f"object[@id='{row['build_object_id']}']/part")
    values={m.get('key'):m.get('value') for m in part.findall('metadata')}
    return np.array([float(values['source_offset_'+axis]) for axis in 'xyz'])

def cad_to_preview(points):
    # CAD X is handle length, CAD Y is face normal, CAD Z is face width.
    # The existing array uses Blender Z as its lift axis and is never rearranged.
    return np.column_stack([points[:,2],points[:,0]-TOUCH_CENTRE_X,points[:,1]+CAD_Y_TO_HEIGHT])

def main():
    base=P/'ModuleArray.blend'
    before=hashlib.sha256(base.read_bytes()).hexdigest()
    handle_before=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
    rows,members=read_source()
    metadata=ET.fromstring(members['Metadata/model_settings.config'])
    bpy.ops.wm.open_mainfile(filepath=str(base))
    scene=bpy.context.scene
    array=list(bpy.data.collections['15 MODULE ARRAY'].objects)
    original_local={o.name:[list(row) for row in o.matrix_basis] for o in array if o.type=='MESH'}
    for obj in array:
        if obj.parent is None:obj.location.z+=ARRAY_LIFT*.001

    collection=bpy.data.collections.new('HANDLE ENCLOSURE - original 3MF geometry')
    scene.collection.children.link(collection)
    material=bpy.data.materials.new('Web enclosure ivory PLA')
    material.use_nodes=True;material.diffuse_color=(.57,.565,.525,1)
    shader=material.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value=(.57,.565,.525,1)
    shader.inputs['Roughness'].default_value=.56;shader.inputs['Metallic'].default_value=0
    shader.inputs['Specular IOR Level'].default_value=.35
    parts=[]
    all_vertices=[]
    for row in rows:
        offset=original_offsets(row,metadata)
        cad=row['v']+offset;vertices=cad_to_preview(cad)
        all_vertices.append(vertices)
        mesh=bpy.data.meshes.new('Enclosure_'+row['name']+'_original_mesh')
        mesh.from_pydata((vertices*.001).tolist(),[],row['f'].tolist());mesh.update()
        # Smooth the original round surfaces while retaining hard slot edges.
        mesh.set_sharp_from_angle(angle=math.radians(35))
        for poly in mesh.polygons:poly.use_smooth=True
        mesh.materials.append(material)
        obj=bpy.data.objects.new('Enclosure_'+row['name'],mesh);collection.objects.link(obj)
        obj['enclosure_part']=row['name'];obj['source_file']='3mf/Handle/inputs/Handle_Original.3mf'
        obj['original_mesh_preserved']=True
        obj['source_offset_xyz_mm']=offset.tolist()
        parts.append({'name':row['name'],'vertices':len(row['v']),'triangles':len(row['f']),
          'original_mesh_preserved':True,'source_offset_xyz_mm':offset.tolist(),
          'cad_bounds_xyz_mm':[cad.min(0).tolist(),cad.max(0).tolist()]})

    bpy.context.view_layer.update()
    aperture_cad=[{'x':[48.,80.],'z':[-16.,-6.]},
                  {'x':[48.,80.],'z':[-4.5,4.5]},
                  {'x':[48.,80.],'z':[6.,16.]}]
    clearances=[]
    for obj in array:
        if obj.type=='MESH':assert original_local[obj.name]==[list(row) for row in obj.matrix_basis]
        if not obj.get('control_dot'):continue
        centre=obj.matrix_world.translation*1000
        radius=max(abs(v.co.x) for v in obj.data.vertices)*1000
        cad_x,cad_z=centre.y+TOUCH_CENTRE_X,centre.x
        fits=[]
        for slot in aperture_cad:
            gap=min(cad_x-radius-slot['x'][0],slot['x'][1]-cad_x-radius,
                    cad_z-radius-slot['z'][0],slot['z'][1]-cad_z-radius)
            if gap>0:fits.append(gap)
        assert len(fits)==1,(obj.name,centre,aperture_cad)
        clearances.extend(fits)
    assert len(clearances)==90
    switch_objects,switch_report=add_tactile_switch(scene)
    scene.camera.location.z+=ARRAY_LIFT*.001
    scene.camera.rotation_euler=(Vector((0,0,(15+ARRAY_LIFT)*.001))-scene.camera.location).to_track_quat('-Z','Y').to_euler()
    bpy.context.preferences.filepaths.save_version=0
    bpy.ops.wm.save_as_mainfile(filepath=str(P/'EnclosedArray.blend'),compress=True)
    bpy.ops.object.select_all(action='DESELECT')
    for obj in array+list(collection.objects)+switch_objects:obj.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(P/'assets/EnclosedArray.glb'),export_format='GLB',
      use_selection=True,export_animations=False,export_cameras=False,export_lights=False,
      export_extras=True,export_apply=True)
    vertices=np.concatenate(all_vertices)
    minimum,maximum=vertices.min(0),vertices.max(0)
    # glTF/Three converts Blender (x,y,z) to (x,z,-y).
    bounds=[[minimum[0],minimum[2],-maximum[1]],[maximum[0],maximum[2],-minimum[1]]]
    report={'source_sha256':before,'blender_source_unchanged':True,'model_file':'EnclosedArray.glb',
      'mesh_instances':332+len(switch_objects),'independent_dots':90,'world_units':'millimetres; glTF geometry is in metres',
      'camera':{'position_mm':[13,110+ARRAY_LIFT,38],'target_mm':[0,15+ARRAY_LIFT,0],'horizontal_fov_degrees':36.243},
      'enclosure':{'source':'3mf/Handle/inputs/Handle_Original.3mf','source_sha256':handle_before,
        'material':'Ivory FDM PLA visual finish: dielectric, matte, 0.2 mm side layers and 0.42 mm top extrusion paths in browser shader',
        'parts':parts,'original_triangle_indices_and_vertices_preserved_before_rigid_transform':True,
        'assembly_frame':'Original STEP coordinates recovered from each part source_offset metadata',
        'cad_touch_window_x_mm':[48,80],'cad_touch_windows_z_mm':[[-16,-6],[-4.5,4.5],[6,16]],
        'array_translation_blender_z_mm':ARRAY_LIFT,'touch_plane_height_mm':23.8+ARRAY_LIFT,
        'all_90_dot_crowns_inside_original_cover_apertures':True,
        'minimum_dot_crown_edge_clearance_mm':min(clearances),'bounds_three_mm':bounds,
        'visual_reference':'paper/竞赛PPT/技术.pptx, slide 1, ppt/media/image10.png',
        'scope':'Visual enclosure assembly; does not establish physical PCB mounting or manufacture fit.'},
      'switch':switch_report}
    (P/'assets/scene.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    (P/'EnclosureVerification.json').write_text(json.dumps(report['enclosure'],indent=2),encoding='utf8')
    (P/'SwitchVerification.json').write_text(json.dumps(switch_report,indent=2),encoding='utf8')
    assert hashlib.sha256(base.read_bytes()).hexdigest()==before
    assert hashlib.sha256(SOURCE.read_bytes()).hexdigest()==handle_before
    print('Enclosed array exported; 90 crowns fit the original cover slots; input files unchanged.',flush=True)

if __name__=='__main__':main()
