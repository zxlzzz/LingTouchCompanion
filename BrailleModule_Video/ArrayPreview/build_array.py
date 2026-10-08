"""Arrange the accepted module appearance using the manufactured PCB placement.

The PCB is viewed after a -90 degree in-plane rotation: native module geometry
then matches the 9-column, 10-row control orientation in ble_testbench.html.
Shared meshes and placements stay intact. surface_finish.py applies the current
photographic materials and light setup after the baseline array is assembled.
"""
from pathlib import Path
import hashlib
import json
import math
import argparse
import sys

import bpy
from mathutils import Vector

sys.path.insert(0, str(Path(__file__).resolve().parent))
from surface_finish import apply_finish

P = Path(__file__).resolve().parent
SOURCE = P.parent / 'MotionPreview' / 'AppearanceStudy.blend'
M = .001
COORDS = [
    (-13.127026, -10.999520), (-13.000025, 0), (-13.000025, 10.999522),
    (-6.627013, -10.999520), (-6.500013, 0), (-6.500013, 10.999522),
    (-.127000, -10.999520), (0, 0), (0, 10.999522),
    (6.373012, -10.999520), (6.500013, 0), (6.500013, 10.999522),
    (12.873025, -10.999520), (13.000025, 0), (12.999578, 10.999522),
]
WIDTH, HEIGHT = 1600, 1100

def aim(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat('-Z', 'Y').to_euler()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--draft', action='store_true')
    parser.add_argument('--scene-only', action='store_true')
    args = parser.parse_args()
    bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
    scene = bpy.context.scene
    source_parts = list(bpy.data.collections['MODULE - static assembly'].objects)
    template = [o for o in source_parts if o.type == 'MESH']
    assert len(template) == 22
    original = {o.name: {'mesh': o.data.name, 'materials': [m.name for m in o.data.materials],
                         'matrix': [list(row) for row in o.matrix_basis]} for o in template}
    tabletop = bpy.data.objects['Tabletop']
    tabletop.location = (0, 0, 0)
    for o in list(bpy.data.objects):
        if o not in source_parts and o != tabletop:
            bpy.data.objects.remove(o, do_unlink=True)
    array = bpy.data.collections.new('15 MODULE ARRAY')
    scene.collection.children.link(array)
    positions = []
    for i, (px, py) in enumerate(COORDS):
        number = i + 1
        root = bpy.data.objects.new(f'Module_{number:02d}', None)
        array.objects.link(root)
        root.location = (py*M, -px*M, 3.8*M)
        root['pcb_designator'] = f'U{31+i}'
        root['control_module'] = number
        root['grid_row'] = (i//3)*2
        root['grid_column'] = (i%3)*3
        for o in template:
            clone = o.copy()
            clone.data = o.data
            clone.name = f'M{number:02d}_{o.name}'
            clone.parent = root
            clone.matrix_parent_inverse.identity()
            clone.matrix_basis = o.matrix_basis.copy()
            clone.animation_data_clear()
            array.objects.link(clone)
            if o.name.startswith('Dot_'):
                # Preserve the user's complete grey-white pin finish without
                # a long cast shadow resembling a differently coloured shaft.
                clone.visible_shadow = False
                dot = int(o.name.split('_')[-1])
                clone['control_dot'] = dot
                clone['control_module'] = number
                clone['grid_row'] = (i//3)*2 + (dot-1)//3
                clone['grid_column'] = (i%3)*3 + 2 - (dot-1)%3
        positions.append({'module': number, 'pcb_designator': f'U{31+i}',
                          'centre_mm': [py, -px, 3.8], 'pcb_relative_mm': [px, py]})
    for o in list(source_parts):
        bpy.data.objects.remove(o, do_unlink=True)
    for c in list(bpy.data.collections):
        if c.name == 'MODULE - static assembly':
            bpy.data.collections.remove(c)
    set_collection = bpy.data.collections.new('ARRAY PHOTOGRAPHIC SET')
    scene.collection.children.link(set_collection)
    for c in list(tabletop.users_collection):
        c.objects.unlink(tabletop)
    set_collection.objects.link(tabletop)

    for name, pos, energy, size, ratio, colour in [
        ('Directional window', (15, 180, 60), 2.8, 28, .68, (1, .985, .91)),
        ('Weak cool room bounce', (90, 15, 70), .045, 110, 1.3, (.79, .86, 1)),
    ]:
        data = bpy.data.lights.new(name, 'AREA')
        data.energy, data.shape = energy, 'RECTANGLE'
        data.size, data.size_y, data.color = size*M, size*ratio*M, colour
        obj = bpy.data.objects.new(name, data)
        set_collection.objects.link(obj)
        obj.location = Vector(pos)*M
        aim(obj, Vector((0, 0, 16))*M)

    data = bpy.data.cameras.new('Array photographic camera')
    camera = bpy.data.objects.new('Array photographic camera', data)
    set_collection.objects.link(camera)
    camera.location = Vector((13, -38, 110))*M
    aim(camera, Vector((0, 0, 15))*M)
    data.type = 'PERSP'
    data.sensor_fit = 'HORIZONTAL'
    data.sensor_width = 36
    data.lens = 55
    data.clip_start, data.clip_end = .00005, 2
    data.dof.use_dof = True
    data.dof.focus_distance = (camera.location - Vector((0, 0, 23.8))*M).length
    # Keep all ninety tactile heads clear in this larger macro framing.
    data.dof.aperture_fstop = 16
    data.dof.aperture_blades = 7
    scene.camera = camera
    scene.render.engine = 'CYCLES'
    scene.render.resolution_x, scene.render.resolution_y = (800, 550) if args.draft else (WIDTH, HEIGHT)
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGB'
    scene.render.image_settings.color_depth = '8'
    scene.render.use_compositing = False
    scene.render.use_sequencer = False
    scene.render.use_border = False
    scene.render.use_crop_to_border = False
    scene.render.use_persistent_data = True
    scene.cycles.samples = 16 if args.draft else 64
    scene.cycles.diffuse_bounces = 4
    scene.cycles.use_denoising = True
    scene.cycles.seed = 0
    scene.cycles.use_animated_seed = False
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'OPTIX'
    prefs.get_devices()
    for device in prefs.devices:
        device.use = device.type == 'OPTIX'
    scene.cycles.device = 'GPU'
    scene['Reference'] = 'Manufacturing PCB positions; PhysicalMotionReference.mp4; accepted single-module appearance.'
    scene['Control_mapping'] = 'ble_testbench.html: 3 2 1 / 6 5 4 in each module, row-major modules.'
    scene['Grid_dimensions'] = [9, 10]
    scene['Pitch_mm'] = [11, 6.5]
    bpy.context.view_layer.update()
    for i in range(1, 16):
        for name, snapshot in original.items():
            clone = bpy.data.objects[f'M{i:02d}_{name}']
            assert clone.data.name == snapshot['mesh']
            assert [m.name for m in clone.data.materials] == snapshot['materials']
            assert [list(row) for row in clone.matrix_basis] == snapshot['matrix']
    assert len([o for o in array.objects if o.type == 'MESH']) == 330
    assert len([o for o in array.objects if o.get('control_dot')]) == 90
    # The accepted camera finish and specular highlight remain unchanged.
    # Disable the pin's volumetric scattering for the large virtual array;
    # its thin 1.42 mm body is presented as opaque grey-white polymer here.
    source_pin_material = bpy.data.objects['M01_Dot_1'].data.materials[0]
    array_pin_material = source_pin_material.copy()
    array_pin_material.name = 'Array grey-white tactile pin finish'
    array_pin_material.node_tree.nodes.get('Principled BSDF').inputs['Subsurface Weight'].default_value = 0
    for obj in array.objects:
        if obj.get('control_dot'):
            obj.data.materials[0] = array_pin_material
    finish = apply_finish(scene, array)
    P.mkdir(exist_ok=True)
    (P/'assets').mkdir(exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(P/'ModuleArray.blend'), compress=True)
    report = {'modules': 15, 'independent_dots': 90, 'mesh_instances': 330,
              'mesh_geometry_and_component_positions_preserved': True,
              'photographic_finish': finish,
              'pin_subsurface_scattering': False,
              'pin_cast_shadows': False,
              'source_sha256': hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
              'pcb_step': '../../3mf/PCB/inputs/3D_PCB1_5_2026-09-15.step',
              'pcb_step_sha256': 'bc137079b08c6e28868dd377544d98e749a99668405f34cabf4c29b9ed15f2aa',
              'pcb_in_plane_rotation_degrees': -90,
              'grid_columns': 9, 'grid_rows': 10, 'pitch_mm': [11, 6.5],
              'positions': positions}
    (P/'ArrayVerification.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    if args.scene_only:
        print('Array scene saved.', flush=True)
        return
    if args.draft:
        (P/'.work').mkdir(exist_ok=True)
    scene.render.filepath = str(P/('.work/Draft.png' if args.draft else 'assets/Base.png'))
    bpy.ops.render.render(write_still=True)
    print('Array scene and photographic base saved.', flush=True)

if __name__ == '__main__':
    main()
