"""Export the existing array geometry for the offline interactive viewer.

The Blender scene is read only. Web materials are assigned by the viewer;
simple export materials avoid baking camera-dependent highlights into meshes.
"""
from pathlib import Path
import hashlib
import json
import bpy

P = Path(__file__).resolve().parent
source = P / 'ModuleArray.blend'
source_hash = hashlib.sha256(source.read_bytes()).hexdigest()
bpy.ops.wm.open_mainfile(filepath=str(source))
bpy.ops.object.select_all(action='DESELECT')
objects = list(bpy.data.collections['15 MODULE ARRAY'].objects)
pins = [o for o in objects if o.get('control_dot')]
assert len(pins) == 90

materials = {}
for name, colour, roughness in [
    ('Web housing top', (.013, .015, .016, 1), .40),
    ('Web housing body', (.008, .010, .012, 1), .43),
    ('Web tactile pin', (.24, .24, .24, 1), .28),
    ('Web internal metal', (.14, .15, .16, 1), .48),
]:
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    shader = mat.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value = colour
    shader.inputs['Roughness'].default_value = roughness
    mat.diffuse_color = colour
    materials[name] = mat

for obj in objects:
    obj.select_set(True)
    if obj.type != 'MESH':
        continue
    original = list(obj.data.materials)
    # Linked mesh slots are replaced once; all instances retain their groups.
    for i, mat in enumerate(original):
        if mat.name.startswith('Web '):
            continue
        if obj.get('control_dot'):
            key = 'Web tactile pin'
        elif 'Housing' in obj.name:
            key = 'Web housing top' if ('top' in mat.name.lower() or 'face' in mat.name.lower()) else 'Web housing body'
        else:
            key = 'Web internal metal' if any(s in mat.name.lower() for s in ['metal', 'steel', 'copper']) else 'Web housing body'
        obj.data.materials[i] = materials[key]

(P / 'assets').mkdir(exist_ok=True)
bpy.ops.export_scene.gltf(
    filepath=str(P / 'assets' / 'ModuleArray.glb'), export_format='GLB',
    use_selection=True, export_animations=False, export_cameras=False,
    export_lights=False, export_extras=True, export_apply=True,
)
assert hashlib.sha256(source.read_bytes()).hexdigest() == source_hash
report = {
    'source_sha256': source_hash, 'blender_source_unchanged': True,
    'mesh_instances': len([o for o in objects if o.type == 'MESH']),
    'independent_dots': len(pins),
    'camera': {'position_mm': [13, 110, 38], 'target_mm': [0, 15, 0], 'horizontal_fov_degrees': 36.243},
    'world_units': 'millimetres; glTF geometry is in metres',
}
(P / 'assets' / 'scene.json').write_text(json.dumps(report, indent=2), encoding='utf8')
print('Web model exported; original scene unchanged.', flush=True)
