"""One editable photographic study from the accepted module and supplied photo.

No compositing effects, wear, geometry edits, raised dots, or animation.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import struct

import bpy
from mathutils import Matrix, Vector

P = Path(__file__).resolve().parent
SOURCE = P.parent / 'BrailleModule.blend'
M = .001
args = argparse.ArgumentParser()
args.add_argument('--width', type=int, default=1200)
args.add_argument('--samples', type=int, default=192)
args.add_argument('--key', type=float, default=2.8)
args.add_argument('--fill', type=float, default=.045)
args.add_argument('--final', action='store_true')
cfg = args.parse_args()

bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
scene = bpy.context.scene
module = bpy.data.collections['MODULE - static assembly']
parts = [o for o in module.objects if o.type == 'MESH']
root = bpy.data.objects['BrailleModule']

def fingerprint(o):
    h = hashlib.sha256()
    for v in o.data.vertices:
        h.update(struct.pack('<3f', *v.co))
    for p in o.data.polygons:
        h.update(struct.pack('<I', len(p.vertices)))
        for i in p.vertices:
            h.update(struct.pack('<I', i))
    for row in o.matrix_basis:
        h.update(struct.pack('<4f', *row))
    return h.hexdigest()

before = {o.name: fingerprint(o) for o in parts}
for o in list(bpy.data.objects):
    if o.name not in module.objects:
        bpy.data.objects.remove(o, do_unlink=True)
for c in list(bpy.data.collections):
    if c != module:
        bpy.data.collections.remove(c)
photo = bpy.data.collections.new('PHOTOGRAPHIC SET')
scene.collection.children.link(photo)

def material(name, colour, roughness, metallic=0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = (*colour, 1)
    bs = mat.node_tree.nodes.get('Principled BSDF')
    bs.inputs['Base Color'].default_value = (*colour, 1)
    bs.inputs['Roughness'].default_value = roughness
    bs.inputs['Metallic'].default_value = metallic
    bs.inputs['IOR'].default_value = 1.49
    return mat, bs

def node(mat, kind, label):
    n = mat.node_tree.nodes.new(kind)
    n.label = label
    return n

def noise(mat, scale, detail, label, vector):
    n = node(mat, 'ShaderNodeTexNoise', label)
    n.inputs['Scale'].default_value = scale
    n.inputs['Detail'].default_value = detail
    n.inputs['Roughness'].default_value = .72
    mat.node_tree.links.new(vector, n.inputs['Vector'])
    return n.outputs['Fac']

def ramp(mat, fac, lo, hi, pos=(.17,.83)):
    n = node(mat, 'ShaderNodeValToRGB', 'Surface variation')
    n.color_ramp.elements[0].position = pos[0]
    n.color_ramp.elements[1].position = pos[1]
    n.color_ramp.elements[0].color = (*lo,1)
    n.color_ramp.elements[1].color = (*hi,1)
    mat.node_tree.links.new(fac, n.inputs[0])
    return n.outputs['Color']

def polymer(name, is_top=False, insert=False):
    mat, bs = material(name, (.0055,.007,.0085), .4)
    tex = node(mat, 'ShaderNodeTexCoord', 'Actual metre coordinates')
    grain = noise(mat, 17000, 2.8, 'Fine mould surface', tex.outputs['Object'])
    broad = noise(mat, 3300, 3.5, 'Mould surface reflection variation', tex.outputs['Object'])
    if insert:
        colours = ((.0028,.0035,.0042),(.009,.0105,.012))
    elif is_top:
        colours = ((.0048,.006,.0072),(.0105,.0125,.0145))
    else:
        colours = ((.0175,.022,.028),(.0175,.022,.028))
    mat.node_tree.links.new(ramp(mat, broad, *colours), bs.inputs['Base Color'])
    rough = (.22,.40) if is_top else (.35,.43)
    mat.node_tree.links.new(ramp(mat, broad, (rough[0],)*3,(rough[1],)*3), bs.inputs['Roughness'])
    bump = node(mat, 'ShaderNodeBump', 'Clean mould texture, no damage')
    bump.inputs['Strength'].default_value = .5 if is_top else .17
    bump.inputs['Distance'].default_value = (.010 if is_top else .0015)*M
    mat.node_tree.links.new(grain,bump.inputs['Height'])
    mat.node_tree.links.new(bump.outputs['Normal'],bs.inputs['Normal'])
    bs.inputs['Specular IOR Level'].default_value = .5
    bs.inputs['Coat Weight'].default_value = .04
    bs.inputs['Coat Roughness'].default_value = .33
    return mat

shell = polymer('Clean black moulded housing')
top = polymer('Clean black tactile face - directional reflection', True)
insert = polymer('Clean black terminal carrier', insert=True)
side, sbs = material('Clean black narrow mould face', (.0055,.007,.0085), .57)
sbs.inputs['Specular IOR Level'].default_value=.28
dot, dbs = material('Grey white smooth tactile polymer', (.075,.095,.105), .22)
dbs.inputs['Specular IOR Level'].default_value = .5
dbs.inputs['Subsurface Weight'].default_value = .055
dbs.inputs['Subsurface Scale'].default_value = .16*M
dbs.inputs['Subsurface Radius'].default_value = (.7,.7,.7)
dot_tex = node(dot,'ShaderNodeTexCoord','Actual metre coordinates')
dot_grain = noise(dot, 34000, 1.5,'Extremely fine clean polymer',dot_tex.outputs['Object'])
dot_bump = node(dot,'ShaderNodeBump','Microscopic clean finish')
dot_bump.inputs['Strength'].default_value = .12
dot_bump.inputs['Distance'].default_value = .0015*M
dot.node_tree.links.new(dot_grain,dot_bump.inputs['Height'])
dot.node_tree.links.new(dot_bump.outputs['Normal'],dbs.inputs['Normal'])
metal, mbs = material('Tin plated contacts', (.55,.59,.62), .23, 1)
for o in parts:
    o.data.materials.clear()
    o.data.materials.append(dot if o.name.startswith('Dot_') else metal if o.name.startswith('Pin_') else insert if o.name=='Base_Insert' else shell)
    for p in o.data.polygons:
        p.material_index = 0
housing = bpy.data.objects['Housing']
housing.data.materials.append(top)
housing.data.materials.append(side)
for p in housing.data.polygons:
    if p.center.z > 19.85*M and p.normal.z > .55:
        p.material_index = 1
    elif abs(p.normal.x) > .85:
        p.material_index = 2

# The back broad face rests on the table, matching the supplied photograph.
root.rotation_euler = (-math.pi/2, 0, 0)
bpy.context.view_layer.update()
lowest = min((o.matrix_world@Vector(v)).z for o in parts for v in o.bound_box)
root.location.z -= lowest
bpy.context.view_layer.update()

table, tbs = material('Warm pale laminate tabletop', (.61,.61,.51), .4)
tc = node(table,'ShaderNodeTexCoord','Actual metre coordinates')
tg = noise(table, 14500, 3,'Fine clean laminate texture', tc.outputs['Object'])
tv = noise(table, 900, 2.3,'Fine laminate surface variation', tc.outputs['Object'])
table.node_tree.links.new(ramp(table,tv,(.53,.55,.46),(.64,.65,.55)),tbs.inputs['Base Color'])
table.node_tree.links.new(ramp(table,tg,(.32,)*3,(.49,)*3),tbs.inputs['Roughness'])
tb = node(table,'ShaderNodeBump','Fine laminate relief')
tb.inputs['Strength'].default_value=.4
tb.inputs['Distance'].default_value=.021*M
table.node_tree.links.new(tg,tb.inputs['Height'])
table.node_tree.links.new(tb.outputs['Normal'],tbs.inputs['Normal'])
tbs.inputs['Specular IOR Level'].default_value=.46
bpy.ops.mesh.primitive_plane_add(size=.6,location=(0,0,0))
ground=bpy.context.object
ground.name='Tabletop'
for c in list(ground.users_collection): c.objects.unlink(ground)
photo.objects.link(ground)
ground.data.materials.append(table)

def local(v): return root.matrix_world@(Vector(v)*M)
def aim(obj,target): obj.rotation_euler=(target-obj.location).to_track_quat('-Z','Y').to_euler()
def area(name, pos, power, size, colour, target, ratio=1):
    d=bpy.data.lights.new(name,'AREA')
    d.energy=power
    d.shape='RECTANGLE'
    d.size=size*M
    d.size_y=size*ratio*M
    d.color=colour
    o=bpy.data.objects.new(name,d)
    photo.objects.link(o)
    o.location=local(pos)
    aim(o,local(target))
    return o

# Physical lights produce the face highlight and long table shadow directly.
area('Directional window', (15,-60,180),cfg.key,28,(1,.985,.91),(0,0,10),.68)
area('Weak cool room bounce', (90,-70,15),cfg.fill,110,(.79,.86,1),(0,0,10),1.3)
scene.world.use_nodes=True
bg=scene.world.node_tree.nodes.get('Background')
bg.inputs['Color'].default_value=(.68,.75,.9,1)
bg.inputs['Strength'].default_value=.1

cd=bpy.data.cameras.new('Photo reference camera')
camera=bpy.data.objects.new('Photo reference camera',cd)
photo.objects.link(camera)
scene.camera=camera
n=Vector((.30,-.61,.73)).normalized()
r=Vector((.55,.76,.40))
r=(r-n*r.dot(n)).normalized()
u=n.cross(r).normalized()
basis=Matrix((r,u,n)).transposed()
camera.rotation_euler=(root.matrix_world.to_3x3()@basis).to_euler()
camera.location=local((0,0,10))+root.matrix_world.to_3x3()@(n*36*M)
cd.type='PERSP'
cd.sensor_fit='VERTICAL'
cd.sensor_height=6.4
cd.lens=7.5
cd.clip_start=.05*M
cd.clip_end=2
focus=bpy.data.objects.new('Focus on tactile face',None)
photo.objects.link(focus)
focus.location=local((0,0,18.4))
focus.hide_render=True
cd.dof.use_dof=True
cd.dof.focus_object=focus
cd.dof.aperture_fstop=8
cd.dof.aperture_blades=7

scene.render.engine='CYCLES'
scene.cycles.samples=cfg.samples
scene.cycles.use_denoising=True
scene.cycles.max_bounces=10
scene.cycles.diffuse_bounces=4
scene.cycles.glossy_bounces=5
scene.cycles.transmission_bounces=6
pref=bpy.context.preferences.addons['cycles'].preferences
try:
    pref.compute_device_type='OPTIX'
    pref.get_devices()
    for device in pref.devices: device.use=device.type=='OPTIX'
    scene.cycles.device='GPU'
except Exception:
    scene.cycles.device='CPU'
scene.render.resolution_x=cfg.width
scene.render.resolution_y=round(cfg.width*4/3)
scene.render.resolution_percentage=100
scene.render.fps=30
scene.render.image_settings.file_format='PNG'
scene.render.image_settings.color_mode='RGB'
scene.render.image_settings.color_depth='8'
scene.render.film_transparent=False
scene.view_settings.view_transform='AgX'
scene.view_settings.look='AgX - Medium High Contrast'
scene.view_settings.exposure=0
scene.view_settings.gamma=1
scene.use_nodes=False
scene.render.use_compositing=False
scene.render.use_sequencer=False
scene.render.filepath=str(P/'ReferenceStudy.png')
scene.unit_settings.system='METRIC'
scene.unit_settings.length_unit='MILLIMETERS'
scene['Reference']='Hsinlung physical module photo; Dot Inc YouTube iSmRM2PUBzA observed at 6, 12, 18, 25, 32, 45 and 51 seconds.'
scene['Scope']='Clean materials and physical lighting; unchanged accepted geometry; no raised dots or animation.'
scene['No_compositor_filters']=True
for area_ui in bpy.context.screen.areas:
    if area_ui.type=='VIEW_3D':
        area_ui.spaces.active.region_3d.view_perspective='CAMERA'
bpy.context.view_layer.update()
assert len(parts)==22
assert all(fingerprint(o)==before[o.name] for o in parts)
assert not bpy.data.actions
bpy.context.preferences.filepaths.save_version=0
bpy.ops.wm.save_as_mainfile(filepath=str(P/'ReferenceStudy.blend'),compress=True)
bpy.ops.render.render(write_still=True)
if cfg.final:
    wide_data=cd.copy()
    wide_data.name='Video closeup camera'
    wide=bpy.data.objects.new('Video closeup camera',wide_data)
    photo.objects.link(wide)
    wn=Vector((.30,-.61,.73)).normalized()
    wr=Vector((0,0,1))
    wr=(wr-wn*wr.dot(wn)).normalized()
    wu=wn.cross(wr).normalized()
    wb=Matrix((wr,wu,wn)).transposed()
    wide.rotation_euler=(root.matrix_world.to_3x3()@wb).to_euler()
    wide.location=local((0,0,15.4))+root.matrix_world.to_3x3()@(wn*31*M)
    wide_data.sensor_fit='HORIZONTAL'
    wide_data.sensor_width=6.4
    wide_data.lens=8.5
    wide_data.dof.aperture_fstop=8
    scene.camera=wide
    scene.render.resolution_x=1920
    scene.render.resolution_y=1080
    scene.render.filepath=str(P/'VideoCloseup.png')
    bpy.ops.render.render(write_still=True)
    # Both cameras remain available; reopen at the reference-photo view.
    scene.camera=camera
    scene.render.resolution_x=cfg.width
    scene.render.resolution_y=round(cfg.width*4/3)
    scene.render.filepath=str(P/'ReferenceStudy.png')
    bpy.ops.wm.save_as_mainfile(filepath=str(P/'ReferenceStudy.blend'),compress=True)
report={'unchanged_parts':22,'geometry_and_local_part_positions_preserved':True,
        'static_retracted_dots':6,'animation':False,'wear':False,'compositor':False,
        'projection':'perspective','resolution':[scene.render.resolution_x,scene.render.resolution_y],
        'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
        'physical_lighting':{'key_W':cfg.key,'fill_W':cfg.fill,'key_local_mm':[15,-60,180]},
        'reference_photo':'../inputs/Touchpoint_Reference.jpg',
        'youtube_video_frames_viewed':True,
        'youtube_reference':'https://www.youtube.com/watch?v=iSmRM2PUBzA',
        'observed_video_times_seconds':[6,12,18,25,32,45,51],
        'video_closeup_resolution':[1920,1080] if cfg.final else None}
(P/'Verification.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print('Reference photographic study saved.')
