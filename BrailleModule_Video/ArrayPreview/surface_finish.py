"""Photographic surface response informed by the supplied physical module clip.

All changes are shader and light settings. World-space texture coordinates make
each module's mould reflection distinct without changing component geometry.
The crown and shaft retain one finish with a bounded camera-facing grey level.
"""
import bpy
from mathutils import Vector


MM = .001


def shader(name, colour, roughness):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.diffuse_color = (*colour, 1)
    bs = mat.node_tree.nodes.get('Principled BSDF')
    bs.inputs['Base Color'].default_value = (*colour, 1)
    bs.inputs['Roughness'].default_value = roughness
    bs.inputs['IOR'].default_value = 1.49
    return mat, bs


def noise(mat, position, scale, detail, label):
    node = mat.node_tree.nodes.new('ShaderNodeTexNoise')
    node.label = label
    node.inputs['Scale'].default_value = scale
    node.inputs['Detail'].default_value = detail
    node.inputs['Roughness'].default_value = .7
    mat.node_tree.links.new(position, node.inputs['Vector'])
    return node.outputs['Fac']


def ramp(mat, value, lo, hi):
    node = mat.node_tree.nodes.new('ShaderNodeValToRGB')
    node.color_ramp.elements[0].position = .22
    node.color_ramp.elements[1].position = .78
    node.color_ramp.elements[0].color = (*lo, 1)
    node.color_ramp.elements[1].color = (*hi, 1)
    mat.node_tree.links.new(value, node.inputs[0])
    return node.outputs['Color']


def housing_material(name, top=False):
    mat, bs = shader(name, (.009, .010, .011), .4)
    links = mat.node_tree.links
    position = mat.node_tree.nodes.new('ShaderNodeNewGeometry').outputs['Position']
    fine = noise(mat, position, 16500, 2, 'Fine mould microrelief')
    middle = noise(mat, position, 2600, 3, 'Uneven mould gloss')
    broad = noise(mat, position, 540, 2.4, 'Slow surface reflection variation')
    colours = ((.007, .008, .009), (.018, .020, .021)) if top else ((.006, .008, .010), (.011, .014, .018))
    links.new(ramp(mat, broad, *colours), bs.inputs['Base Color'])
    roughness = (.25, .55) if top else (.36, .50)
    links.new(ramp(mat, middle, (roughness[0],)*3, (roughness[1],)*3), bs.inputs['Roughness'])
    bump = mat.node_tree.nodes.new('ShaderNodeBump')
    bump.label = 'Mould surface, not damage or dirt'
    bump.inputs['Strength'].default_value = .29 if top else .14
    bump.inputs['Distance'].default_value = (.008 if top else .002)*MM
    links.new(fine, bump.inputs['Height'])
    coarse = mat.node_tree.nodes.new('ShaderNodeBump')
    coarse.inputs['Strength'].default_value = .22 if top else .10
    coarse.inputs['Distance'].default_value = (.012 if top else .003)*MM
    links.new(middle, coarse.inputs['Height'])
    links.new(bump.outputs['Normal'], coarse.inputs['Normal'])
    links.new(coarse.outputs['Normal'], bs.inputs['Normal'])
    bs.inputs['Specular IOR Level'].default_value = .50 if top else .35
    bs.inputs['Coat Weight'].default_value = 0
    return mat


def pin_material():
    mat, bs = shader('Photographic neutral grey-white complete pins', (.14,)*3, .24)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bs.inputs['Subsurface Weight'].default_value = 0
    bs.inputs['Specular IOR Level'].default_value = .8
    tex = nodes.new('ShaderNodeTexCoord')
    info = nodes.new('ShaderNodeObjectInfo')
    info.label = 'Stable mould finish variation per complete pin'
    offset = nodes.new('ShaderNodeVectorMath')
    offset.operation = 'ADD'
    links.new(tex.outputs['Object'], offset.inputs[0])
    links.new(info.outputs['Random'], offset.inputs[1])
    fine = noise(mat, offset.outputs[0], 32000, 1.5, 'Subtle pin surface')
    waves = noise(mat, offset.outputs[0], 1400, 1.3, 'Shallow cap-scale mould waviness')
    roughness = nodes.new('ShaderNodeMapRange')
    roughness.label = 'Small manufacturing gloss differences'
    roughness.inputs['To Min'].default_value = .16
    roughness.inputs['To Max'].default_value = .34
    links.new(info.outputs['Random'], roughness.inputs['Value'])
    links.new(roughness.outputs[0], bs.inputs['Roughness'])
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = .07
    bump.inputs['Distance'].default_value = .0008*MM
    links.new(fine, bump.inputs['Height'])
    shallow = nodes.new('ShaderNodeBump')
    shallow.inputs['Strength'].default_value = .65
    shallow.inputs['Distance'].default_value = .050*MM
    links.new(waves, shallow.inputs['Height'])
    links.new(bump.outputs['Normal'], shallow.inputs['Normal'])
    links.new(shallow.outputs['Normal'], bs.inputs['Normal'])
    # A low-contrast base preserves the accepted full-colour cylindrical shaft.
    # Only the polymer's Fresnel reflection supplies the highlight. The former
    # additive glossy branch exaggerated one repeated bright spot on every crown.
    display = nodes.new('ShaderNodeEmission')
    display.name = 'Grey camera base shared by crown and shaft'
    display.inputs['Color'].default_value = (.52, .52, .52, 1)
    display.inputs['Strength'].default_value = 1
    mix = nodes.new('ShaderNodeMixShader')
    mix.name = 'Bounded physical response'
    mix.inputs[0].default_value = .60
    links.new(display.outputs[0], mix.inputs[1])
    links.new(bs.outputs[0], mix.inputs[2])
    rays = nodes.new('ShaderNodeLightPath')
    camera_mix = nodes.new('ShaderNodeMixShader')
    links.new(rays.outputs['Is Camera Ray'], camera_mix.inputs[0])
    links.new(bs.outputs[0], camera_mix.inputs[1])
    links.new(mix.outputs[0], camera_mix.inputs[2])
    links.new(camera_mix.outputs[0], nodes.get('Material Output').inputs['Surface'])
    return mat


def apply_finish(scene, collection):
    top = housing_material('Photographic black tactile face with broken gloss', True)
    broad = housing_material('Photographic black moulded broad face')
    narrow = housing_material('Photographic black moulded narrow face')
    pin = pin_material()
    for obj in collection.objects:
        if obj.type != 'MESH':
            continue
        if obj.name.endswith('_Housing'):
            # Existing face assignments identify the tactile, broad and narrow faces.
            obj.data.materials[0] = broad
            obj.data.materials[1] = top
            obj.data.materials[2] = narrow
        elif obj.get('control_dot'):
            obj.data.materials[0] = pin
            obj.visible_shadow = False

    key = bpy.data.objects['Directional window']
    key.location = Vector((-30, 75, 190))*MM
    key.rotation_euler = (Vector((0, 0, 23.8))*MM-key.location).to_track_quat('-Z', 'Y').to_euler()
    key.data.energy = .45
    key.data.size = 70*MM
    key.data.size_y = 35*MM
    key.data.color = (1, .985, .955)
    fill = bpy.data.objects['Weak cool room bounce']
    fill.data.energy = .06
    fill.data.color = (.93, .97, 1)
    scene['Appearance_reference'] = 'inputs/Touchpoint_Reference.jpg and PhysicalMotionReference.mp4, frames 45 and 91.'
    scene['Appearance_scope'] = 'Moulded surface reflection and grey-white complete pins; physical lighting; no dirt, wear or compositor filters.'
    scene['Appearance_revision'] = 4
    return {'revision': 4, 'reference_frames': [45, 91],
            'world_space_mould_texture': True, 'shared_pin_finish': pin.name,
            'camera_pin_base_linear_rgb': [.52]*3,
            'pin_physical_fraction': .60, 'pin_cast_shadows': False,
            'additive_glossy_highlight': False,
            'pin_roughness_range': [.16, .34], 'stable_per_pin_surface_variation': True,
            'key_position_mm': [-30, 75, 190], 'key_size_mm': [70, 35],
            'wear': False, 'compositor_filters': False}
