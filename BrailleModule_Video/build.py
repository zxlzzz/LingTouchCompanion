"""Build the complete static exterior from the supplier PDF, in millimetres.

Produces an editable Blender scene, a material-aware GLB and a coloured STEP
assembly from the same geometry. The independent dots have no animation.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import struct
import numpy as np
import trimesh
import bpy
from mathutils import Vector
from OCP.gp import gp_Pnt, gp_Dir, gp_Ax2, gp_Vec, gp_Trsf
from OCP.BRep import BRep_Tool
from OCP.BRepAdaptor import BRepAdaptor_Surface
from OCP.BRepPrimAPI import BRepPrimAPI_MakeBox, BRepPrimAPI_MakeCylinder, BRepPrimAPI_MakeCone, BRepPrimAPI_MakeSphere
from OCP.BRepAlgoAPI import BRepAlgoAPI_Cut, BRepAlgoAPI_Fuse
from OCP.BRepFilletAPI import BRepFilletAPI_MakeFillet
from OCP.BRepBuilderAPI import BRepBuilderAPI_MakePolygon, BRepBuilderAPI_Transform
from OCP.BRepOffsetAPI import BRepOffsetAPI_ThruSections
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRepCheck import BRepCheck_Analyzer
from OCP.BRepBndLib import BRepBndLib
from OCP.Bnd import Bnd_Box
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE, TopAbs_EDGE, TopAbs_SOLID, TopAbs_REVERSED
from OCP.TopoDS import TopoDS
from OCP.TopLoc import TopLoc_Location
from OCP.TDocStd import TDocStd_Document
from OCP.TCollection import TCollection_ExtendedString
from OCP.TDataStd import TDataStd_Name
from OCP.XCAFDoc import XCAFDoc_DocumentTool, XCAFDoc_ColorType
from OCP.Quantity import Quantity_Color, Quantity_TOC_RGB
from OCP.STEPCAFControl import STEPCAFControl_Writer
from OCP.STEPControl import STEPControl_AsIs, STEPControl_Reader
from OCP.IFSelect import IFSelect_RetDone
from OCP.GeomAbs import GeomAbs_Sphere

P = Path(__file__).resolve().parent
D = json.loads((P / 'parameters.json').read_text(encoding='utf8'))
M = 0.001  # Blender and GLB coordinates are actual metres.
PARTS = []
REPORT = {'source_sha256': hashlib.sha256((P / D['source']['file']).read_bytes()).hexdigest(),
          'touchpoint_photo_sha256': hashlib.sha256((P / D['source']['touchpoint_photo']).read_bytes()).hexdigest(),
          'parts': []}
COLOURS = {
    'Black housing': ((0.0035, 0.0040, 0.0048), 0.0, 0.46),
    'Black base insert': ((0.0018, 0.0020, 0.0024), 0.0, 0.56),
    'Grey white tactile dots': ((0.68, 0.69, 0.68), 0.0, 0.34),
    'Tin plated terminals': ((0.64, 0.67, 0.70), 1.0, 0.30),
}


def box(x0, x1, y0, y1, z0, z1):
    return BRepPrimAPI_MakeBox(gp_Pnt(x0, y0, z0), x1-x0, y1-y0, z1-z0).Shape()


def cylinder(x, y, z, r, h, direction=(0, 0, 1)):
    return BRepPrimAPI_MakeCylinder(gp_Ax2(gp_Pnt(x, y, z), gp_Dir(*direction)), r, h).Shape()


def round_headed_dot():
    """A true spherical cap over a hidden stem, with its apex at local Z=0."""
    a, h = D['dot_diameter']/2, D['dot_cap_height']
    radius = (a*a+h*h)/(2*h)
    sphere = BRepPrimAPI_MakeSphere(gp_Pnt(0, 0, -radius), radius).Shape()
    cut_below = box(-radius-0.1, radius+0.1, -radius-0.1, radius+0.1, -2*radius-0.1, -h)
    cap = boolean(sphere, cut_below)
    stem = cylinder(0, 0, -0.85, a, 0.85-h)
    return boolean(cap, stem, False)


def boolean(a, b, subtract=True):
    op = (BRepAlgoAPI_Cut if subtract else BRepAlgoAPI_Fuse)(a, b)
    op.SetFuzzyValue(1e-7)
    op.Build()
    if not op.IsDone():
        raise RuntimeError('CAD boolean failed')
    return op.Shape()


def rounded(shape, radius):
    f = BRepFilletAPI_MakeFillet(shape)
    it = TopExp_Explorer(shape, TopAbs_EDGE)
    while it.More():
        f.Add(radius, TopoDS.Edge(it.Current()))
        it.Next()
    f.Build()
    if not f.IsDone():
        raise RuntimeError(f'Fillet failed, radius {radius}')
    return f.Shape()


def capsule_slot(x, face_y, z, depth, width=0.55, height=1.65):
    """Shallow capsule-shaped moulding recess on a broad housing face."""
    r = width/2
    y0 = face_y-depth if face_y > 0 else face_y-0.02
    y1 = face_y+0.02 if face_y > 0 else face_y+depth
    middle = box(x-r, x+r, y0, y1, z-height/2+r, z+height/2-r)
    for zz in [z-height/2+r, z+height/2-r]:
        middle = boolean(middle, cylinder(x, y0, zz, r, y1-y0, (0, 1, 0)), False)
    return middle


def stamped_pin(x, side, index):
    """A solid loft of the thin stamped terminal, including its shoulder and jog."""
    row_y = (D['pin_inner_row_gap'] + D['pin_thickness'])/2
    shoulder_offset = [-0.30, 0.18, 0.28, 0.10, -0.15, -0.26][index]
    stages = [
        (0.28, 0.93, x+shoulder_offset, 2.68),
        (-0.62, 0.93, x+shoulder_offset, 2.68),
        (-0.88, 0.93, x+shoulder_offset, row_y),
        (-1.38, 0.93, x+shoulder_offset, row_y),
        (-1.56, D['pin_width'], x, row_y),
        (-D['pin_extension'], D['pin_width'], x, row_y),
    ]
    loft = BRepOffsetAPI_ThruSections(True, True, 1e-8)
    loft.CheckCompatibility(False)
    for z, width, cx, cy in stages:
        y = side*cy
        t = D['pin_thickness']/2
        wire = BRepBuilderAPI_MakePolygon()
        for xx, yy in [(cx-width/2, y-t), (cx+width/2, y-t), (cx+width/2, y+t), (cx-width/2, y+t)]:
            wire.Add(gp_Pnt(xx, yy, z))
        wire.Close()
        loft.AddWire(wire.Wire())
    loft.Build()
    if not loft.IsDone():
        raise RuntimeError('Terminal loft failed')
    return loft.Shape()


def part(name, shape, material, location=(0, 0, 0), **metadata):
    if not BRepCheck_Analyzer(shape).IsValid():
        raise RuntimeError(f'Invalid CAD part: {name}')
    it = TopExp_Explorer(shape, TopAbs_SOLID)
    count = 0
    while it.More():
        count += 1
        it.Next()
    if count != 1:
        raise RuntimeError(f'{name}: expected one connected solid, got {count}')
    PARTS.append({'name': name, 'shape': shape, 'material': material, 'location': location, 'metadata': metadata})


def geometry():
    w, d, h, base = D['body_width']/2, D['body_depth']/2, D['body_height'], D['base_height']
    shell = rounded(box(-w, w, -d, d, base, h), D['edge_radius'])
    wall = D['shell_wall']
    shell = boolean(shell, rounded(box(-w+wall, w-wall, -d+wall, d-wall, base-0.02, h-D['shell_top_thickness']), 0.045))
    for row, y in enumerate([-D['dot_pitch']/2, D['dot_pitch']/2]):
        for col, x in enumerate([-D['dot_pitch'], 0, D['dot_pitch']]):
            aperture = cylinder(x, y, h-1.0, D['dot_aperture_diameter']/2, 1.1)
            shell = boolean(shell, aperture)
            mouth = BRepPrimAPI_MakeCone(gp_Ax2(gp_Pnt(x, y, h-0.12), gp_Dir(0, 0, 1)),
                D['dot_aperture_diameter']/2, D['dot_aperture_mouth_diameter']/2, 0.12).Shape()
            shell = boolean(shell, mouth)
    for x, z in [(-2.5, 16.8), (2.5, 16.8), (0, 9.0)]:
        shell = boolean(shell, capsule_slot(x, -d, z, 0.15))
    for x in [-2.5, 2.5]:
        shell = boolean(shell, capsule_slot(x, d, 5.8, 0.15))
    part('Housing', shell, 'Black housing', role='Exterior housing; unverified internal wall thickness')

    collar_w = D['base_collar_width']/2
    collar = rounded(box(-collar_w, collar_w, -d, d, 1.2, base), 0.045)
    for side in [-1, 1]:
        # Two end channels leave four distinct projecting mounting shoulders.
        x0, x1 = (w+0.025, collar_w+0.02) if side > 0 else (-collar_w-0.02, -w-0.025)
        collar = boolean(collar, box(x0, x1, -1.23, 1.23, 1.18, 3.18))
    slots = [-2.57, -1.82, -1.16, -0.33, 0.68, 1.42, 2.27, 3.40]
    for side in [-1, 1]:
        for i, x in enumerate(slots):
            if side > 0:
                x = -x
            width = 0.38 if i in [2, 5] else 0.13
            y0, y1 = (2.77, 3.03) if side > 0 else (-3.03, -2.77)
            collar = boolean(collar, box(x-width/2, x+width/2, y0, y1, 1.18, 2.80))
    part('Base_Collar', collar, 'Black housing', role='Four mounting shoulders and slotted collar')

    insert = rounded(box(-4.98, 4.98, -2.98, 2.98, 0, 2.42), 0.04)
    for side in [-1, 1]:
        y0, y1 = (2.935, 3.02) if side > 0 else (-3.02, -2.935)
        insert = boolean(insert, box(-4.05, 4.05, y0, y1, 0.18, 1.80))
        # Fine moulding divisions follow the visible terminal carrier, not an invented circuit.
        for x in [-3.7, -2.6, -1.5, -0.4, 0.7, 1.8, 2.9, 4.0]:
            y0, y1 = (2.82, 3.01) if side > 0 else (-3.01, -2.82)
            insert = boolean(insert, box(x-0.025, x+0.025, y0, y1, 0.18, 1.82))
    part('Base_Insert', insert, 'Black base insert', role='Visible terminal carrier; material colour estimated')

    key_end = D['base_overall_width'] - collar_w
    key = rounded(box(4.92, key_end, -0.79, 0.79, 0.56, 1.20), 0.045)
    part('Orientation_Tab', key, 'Black housing', role='Asymmetric locating tab')

    # The offset dimensions are in opposite broad-side views. Reverse the second view.
    front_last = key_end-D['pin_front_end_offset']-D['pin_width']/2
    front_x = [front_last-(5-i)*D['pin_pitch'] for i in range(6)]
    back_last = key_end-D['pin_back_end_offset']-D['pin_width']/2
    back_x = [back_last-(5-i)*D['pin_pitch'] for i in range(6)]
    for row, (side, positions) in enumerate([(-1, front_x), (1, back_x)]):
        for i, x in enumerate(positions):
            number = i+1+row*6
            part(f'Pin_{number:02d}', stamped_pin(x, side, i), 'Tin plated terminals',
                 role='External terminal', geometric_terminal_index=number,
                 electrical_assignment='Not established by this exterior model', tail_centre_mm=[x, side*2.53])

    # Looking at the tactile face with the locating tab at the top (+X):
    # 1/2/3 are the left column (+Y), 4/5/6 the right column (-Y), PDF p6.
    for row, y in enumerate([D['dot_pitch']/2, -D['dot_pitch']/2]):
        for col, x in enumerate([D['dot_pitch'], 0, -D['dot_pitch']]):
            number = col+1+row*3
            # A rounded crown replaces the former flat-topped visible cylinder.
            # The apex stays flush; the curved sides sit inside the existing aperture.
            dot = round_headed_dot()
            part(f'Dot_{number}', dot, 'Grey white tactile dots', (x, y, D['dot_visible_top_z']),
                 role='Independent tactile dot', dot_number=number,
                 head_shape='Spherical cap', cap_height_mm=D['dot_cap_height'],
                 rest_state='Retracted; apex flush; no animation',
                 motion_axis='Local +Z')


def world_shape(p):
    tr = gp_Trsf()
    tr.SetTranslation(gp_Vec(*p['location']))
    return BRepBuilderAPI_Transform(p['shape'], tr, True).Shape()


def bounds(shape):
    b = Bnd_Box()
    BRepBndLib.AddOptimal_s(shape, b, False, False)
    lo, hi = b.CornerMin(), b.CornerMax()
    return np.array([[lo.X(), lo.Y(), lo.Z()], [hi.X(), hi.Y(), hi.Z()]])


def mesh(shape, spherical_tip=False):
    BRepMesh_IncrementalMesh(shape, 0.008, False, 0.12, True).Perform()
    vertices, triangles, corner_normals = [], [], []
    it = TopExp_Explorer(shape, TopAbs_FACE)
    while it.More():
        face = TopoDS.Face(it.Current())
        loc = TopLoc_Location()
        tri = BRep_Tool.Triangulation_s(face, loc)
        if tri is None:
            raise RuntimeError('Missing face triangulation')
        start = len(vertices)
        tr = loc.Transformation()
        surface = BRepAdaptor_Surface(face)
        normals = []
        for i in range(1, tri.NbNodes()+1):
            node = tri.Node(i).Transformed(tr)
            vertices.append([node.X(), node.Y(), node.Z()])
            uv = tri.UVNode(i)
            point, du, dv = gp_Pnt(), gp_Vec(), gp_Vec()
            surface.D1(uv.X(), uv.Y(), point, du, dv)
            normal = du.Crossed(dv)
            if spherical_tip and normal.Magnitude() < 1e-12 and surface.GetType() == GeomAbs_Sphere:
                normal = gp_Vec(surface.Sphere().Location(), node)
            if normal.Magnitude() < 1e-12:
                normal = gp_Vec(0, 0, 0)
            else:
                normal.Normalize()
                if face.Orientation() == TopAbs_REVERSED:
                    normal.Reverse()
            normals.append([normal.X(), normal.Y(), normal.Z()])
        for i in range(1, tri.NbTriangles()+1):
            a, b, c = tri.Triangle(i).Get()
            if face.Orientation() == TopAbs_REVERSED:
                b, c = c, b
            triangles.append([start+a-1, start+b-1, start+c-1])
            corner_normals.append([normals[a-1], normals[b-1], normals[c-1]])
        it.Next()
    q = trimesh.Trimesh(vertices=np.asarray(vertices), faces=np.asarray(triangles), process=False)
    q.merge_vertices(digits_vertex=6)
    keep = q.nondegenerate_faces()
    q.update_faces(keep)
    corner_normals = np.asarray(corner_normals)[keep]
    q.remove_unreferenced_vertices()
    if not q.is_watertight or not q.is_winding_consistent or q.volume <= 0:
        raise RuntimeError('Invalid tessellation')
    zero = np.linalg.norm(corner_normals, axis=2) < 0.5
    corner_normals[zero] = np.repeat(q.face_normals[:, None, :], 3, axis=1)[zero]
    return q, corner_normals


def srgb(x):
    return 12.92*x if x <= 0.0031308 else 1.055*x**(1/2.4)-0.055


def export_step():
    doc = TDocStd_Document(TCollection_ExtendedString('Braille Module'))
    shape_tool = XCAFDoc_DocumentTool.ShapeTool_s(doc.Main())
    colour_tool = XCAFDoc_DocumentTool.ColorTool_s(doc.Main())
    root = shape_tool.NewShape()
    TDataStd_Name.Set_s(root, TCollection_ExtendedString('BrailleModule_Static'))
    for p in PARTS:
        label = shape_tool.AddShape(world_shape(p), False)
        TDataStd_Name.Set_s(label, TCollection_ExtendedString(p['name']))
        colour = Quantity_Color(*[srgb(c) for c in COLOURS[p['material']][0]], Quantity_TOC_RGB)
        colour_tool.SetColor(label, colour, XCAFDoc_ColorType.XCAFDoc_ColorGen)
        shape_tool.AddComponent(root, label, TopLoc_Location())
    shape_tool.UpdateAssemblies()
    writer = STEPCAFControl_Writer()
    writer.SetColorMode(True)
    writer.SetNameMode(True)
    if not writer.Transfer(doc, STEPControl_AsIs) or writer.Write(str(P/'BrailleModule.step')) != IFSelect_RetDone:
        raise RuntimeError('STEP export failed')
    reader = STEPControl_Reader()
    assert reader.ReadFile(str(P/'BrailleModule.step')) == IFSelect_RetDone
    reader.TransferRoots()
    assert BRepCheck_Analyzer(reader.OneShape()).IsValid()
    REPORT['step_readback_bounds_mm'] = bounds(reader.OneShape()).tolist()


def material(name):
    rgb, metal, rough = COLOURS[name]
    m = bpy.data.materials.new(name)
    m.diffuse_color = (*rgb, 1)
    m.use_nodes = True
    bsdf = m.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = (*rgb, 1)
    bsdf.inputs['Metallic'].default_value = metal
    bsdf.inputs['Roughness'].default_value = rough
    if name.startswith('Black'):
        bsdf.inputs['Specular IOR Level'].default_value = 0.25
    return m


def aim(obj, position):
    obj.rotation_euler = (Vector(position)-obj.location).to_track_quat('-Z', 'Y').to_euler()


def area_light(collection, name, position, power, size, target):
    data = bpy.data.lights.new(name, 'AREA')
    data.energy = power
    data.shape = 'DISK'
    data.size = size*M
    obj = bpy.data.objects.new(name, data)
    collection.objects.link(obj)
    obj.location = Vector(position)*M
    aim(obj, Vector(target)*M)


def blender_scene(render=True):
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version = 0
    scene = bpy.context.scene
    scene.unit_settings.system = 'METRIC'
    scene.unit_settings.length_unit = 'MILLIMETERS'
    scene.unit_settings.scale_length = 1.0
    models = bpy.data.collections.new('MODULE - static assembly')
    scene.collection.children.link(models)
    studio = bpy.data.collections.new('STUDIO - preview only')
    scene.collection.children.link(studio)
    materials = {name: material(name) for name in COLOURS}
    root = bpy.data.objects.new('BrailleModule', None)
    root.empty_display_type = 'PLAIN_AXES'
    root.empty_display_size = 1.5*M
    models.objects.link(root)
    root['reference'] = D['source']['file']
    root['state'] = 'Static exterior; six independently movable round-headed dots; apices flush'
    root['dimensioned_body_mm'] = [D['body_width'], D['body_depth'], D['body_height']]
    model_objects = []
    for p in PARTS:
        q, corner_normals = mesh(p['shape'], spherical_tip=p['name'].startswith('Dot_'))
        data = bpy.data.meshes.new(p['name']+'_Mesh')
        data.from_pydata((q.vertices*M).tolist(), [], q.faces.tolist())
        data.materials.append(materials[p['material']])
        # CAD face normals retain hard edges; curved CAD surfaces interpolate smoothly.
        data.polygons.foreach_set('use_smooth', [True]*len(data.polygons))
        data.normals_split_custom_set(corner_normals.reshape(-1, 3).tolist())
        obj = bpy.data.objects.new(p['name'], data)
        models.objects.link(obj)
        obj.parent = root
        obj.location = Vector(p['location'])*M
        for key, value in p['metadata'].items():
            obj[key] = value
        obj['geometry_units'] = 'metres; UI displays millimetres'
        model_objects.append(obj)
        REPORT['parts'].append({'name': p['name'], 'bounds_mm': bounds(world_shape(p)).tolist(),
            'watertight': bool(q.is_watertight), 'winding_consistent': bool(q.is_winding_consistent),
            'volume_mm3': float(q.volume), 'triangles': len(q.faces)})
    # Export only the physical assembly; retain separate dots and terminals.
    bpy.ops.object.select_all(action='DESELECT')
    root.select_set(True)
    for obj in model_objects:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = root
    bpy.ops.export_scene.gltf(filepath=str(P/'BrailleModule.glb'), export_format='GLB',
        use_selection=True, export_animations=False, export_cameras=False, export_lights=False,
        export_extras=True, export_apply=True)

    camera_data = bpy.data.cameras.new('Product Camera')
    camera = bpy.data.objects.new('Product Camera', camera_data)
    studio.objects.link(camera)
    scene.camera = camera
    camera_data.type = 'ORTHO'
    camera_data.clip_start = 0.05*M
    camera_data.clip_end = 1000*M
    camera_data.ortho_scale = 35*M
    camera.location = Vector((38, -57, 46))*M
    aim(camera, Vector((0, 0, 8.5))*M)
    area_light(studio, 'Key softbox', (-24, -30, 48), 0.063, 30, (0, 0, 10))
    area_light(studio, 'Rim softbox', (18, 18, 32), 0.077, 22, (0, 0, 10))
    area_light(studio, 'Front fill', (15, -30, 4), 0.019, 22, (0, 0, 8))
    world = bpy.data.worlds.new('Studio white')
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.65, 0.65, 0.65, 1)
    world.node_tree.nodes['Background'].inputs['Strength'].default_value = 0.35
    scene.world = world
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 64
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 1600
    scene.render.resolution_y = 1600
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    scene.render.film_transparent = True
    scene.view_settings.view_transform = 'AgX'
    # White background independent of the lighting, for legible black plastic previews.
    scene.use_nodes = True
    nodes = scene.node_tree.nodes
    nodes.clear()
    layers = nodes.new('CompositorNodeRLayers')
    over = nodes.new('CompositorNodeAlphaOver')
    over.inputs[0].default_value = 1.0
    over.inputs[1].default_value = (8, 8, 8, 1)
    output = nodes.new('CompositorNodeComposite')
    scene.node_tree.links.new(layers.outputs['Image'], over.inputs[2])
    scene.node_tree.links.new(over.outputs['Image'], output.inputs[0])
    scene.render.filepath = str(P/'Preview.png')
    # Comfortable starting viewport and clearly separated studio/model collections.
    for screen in bpy.data.screens:
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                area.spaces.active.clip_start = 0.02*M
                area.spaces.active.clip_end = 1000*M
                area.spaces.active.region_3d.view_distance = 40*M
                area.spaces.active.region_3d.view_location = Vector((0, 0, 8.5))*M
                area.spaces.active.region_3d.view_rotation = camera.rotation_euler.to_quaternion()
                area.spaces.active.shading.type = 'MATERIAL'
                area.spaces.active.overlay.show_floor = False
                area.spaces.active.overlay.show_axis_x = False
                area.spaces.active.overlay.show_axis_y = False
    bpy.ops.object.select_all(action='DESELECT')
    bpy.context.view_layer.objects.active = model_objects[0]
    model_objects[0].select_set(True)
    bpy.ops.wm.save_as_mainfile(filepath=str(P/'BrailleModule.blend'))
    if render:
        bpy.ops.render.render(write_still=True)
        scene.render.filepath = str(P/'Preview_Dots.png')
        camera.location = Vector((9, -14, 30))*M
        aim(camera, Vector((0, 0, 19.7))*M)
        camera_data.ortho_scale = 11.5*M
        scene.render.resolution_x = 1600
        scene.render.resolution_y = 1100
        bpy.ops.render.render(write_still=True)
        scene.render.filepath = str(P/'Preview_Back.png')
        camera.location = Vector((-38, 57, 28))*M
        aim(camera, Vector((0, 0, 8.5))*M)
        camera_data.ortho_scale = 35*M
        scene.render.resolution_x = 1600
        scene.render.resolution_y = 1600
        bpy.ops.render.render(write_still=True)
        scene.render.filepath = str(P/'Preview_Top.png')
        camera.location = Vector((0, 0, 65))*M
        aim(camera, Vector((0, 0, 0))*M)
        camera_data.ortho_scale = 14*M
        scene.render.resolution_x = 1400
        scene.render.resolution_y = 1000
        bpy.ops.render.render(write_still=True)


def verify_glb():
    data = (P/'BrailleModule.glb').read_bytes()
    magic, version, total = struct.unpack_from('<III', data)
    assert magic == 0x46546C67 and version == 2 and total == len(data)
    json_size, chunk_type = struct.unpack_from('<II', data, 12)
    assert chunk_type == 0x4E4F534A
    gltf = json.loads(data[20:20+json_size])
    assert 'animations' not in gltf
    assert len([n for n in gltf['nodes'] if n.get('name', '').startswith('Dot_')]) == 6
    assert len([n for n in gltf['nodes'] if n.get('name', '').startswith('Pin_')]) == 12
    scene = trimesh.load(P/'BrailleModule.glb', force='scene')
    # glTF is Y-up: X width, Y height, Z depth.
    extents = scene.bounds[1]-scene.bounds[0]
    expected = np.array([D['base_overall_width'], D['body_height']+D['pin_extension'], D['body_depth']])*M
    assert np.allclose(extents, expected, atol=2e-7), (extents, expected)
    REPORT['glb_bounds_m'] = scene.bounds.tolist()
    REPORT['glb_readback_extent_mm'] = (extents/M).tolist()
    REPORT['glb_named_dots'] = 6
    REPORT['glb_named_terminals'] = 12
    REPORT['animations'] = 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--no-render', action='store_true')
    args = parser.parse_args()
    geometry()
    export_step()
    blender_scene(render=not args.no_render)
    verify_glb()
    for p in REPORT['parts']:
        if p['name'].startswith('Dot_'):
            assert abs(p['bounds_mm'][1][2]-D['body_height']) < 1e-6
    assert len(PARTS) == 22
    REPORT['part_count'] = len(PARTS)
    REPORT['pass'] = True
    REPORT['limitations'] = 'Exterior reconstruction. Unmarked dimensions follow drawing proportions; no verified internal mechanism.'
    (P/'Verification.json').write_text(json.dumps(REPORT, indent=2), encoding='utf8')
    print('Built and verified complete 22-part module. Six round-headed dots, apices flush; no animation.', flush=True)


if __name__ == '__main__':
    main()
