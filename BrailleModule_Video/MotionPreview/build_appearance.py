"""Refine the six tactile pins in a copy of the accepted photographic scene.

The original scene is immutable. The spherical crowns retain their profile above
local -0.40 mm. A 0.10 mm tangent transition joins each crown to its straight
1.42 mm diameter shaft, avoiding an apparent separate collar in the lighting.
This builds and verifies the editable appearance scene without rendering.
For the preview, camera rays see a low-contrast grey-white display finish. Other
ray paths retain the physical polymer shader, without any added scene lights.
"""
from pathlib import Path
from collections import Counter
import hashlib
import json
import math
import struct

import bpy


HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent / "PhotoStudy" / "ReferenceStudy.blend"
OUTPUT = HERE / "AppearanceStudy.blend"
REPORT = HERE / "AppearanceVerification.json"
MM = .001
RADIUS = .710
CAP_HEIGHT = .450
SPHERE_RADIUS = (RADIUS * RADIUS + CAP_HEIGHT * CAP_HEIGHT) / (2 * CAP_HEIGHT)
SHAFT_BOTTOM = -.850
BLEND_BOTTOM = -.500
BLEND_TOP = -.400
SECTORS = 128
BLEND_STEPS = 12
CAP_STEPS = 32
COLOUR = (.105, .105, .105)
ROUGHNESS = .28
SSS_WEIGHT = .10
SSS_SCALE_MM = .30
DISPLAY_RGB = (.9, .9, .9)
DISPLAY_PBR_MIX = .12


def file_hash(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mesh_hash(mesh):
    h = hashlib.sha256()
    for vertex in mesh.vertices:
        h.update(struct.pack("<3f", *vertex.co))
    for polygon in mesh.polygons:
        h.update(struct.pack("<II", len(polygon.vertices), polygon.material_index))
        for index in polygon.vertices:
            h.update(struct.pack("<I", index))
    for normal in mesh.corner_normals:
        h.update(struct.pack("<3f", *normal.vector))
    return h.hexdigest()


def json_value(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    try:
        return list(value)
    except TypeError:
        return str(value)


def material_hash(mat):
    payload = {"colour": list(mat.diffuse_color), "use_nodes": mat.use_nodes,
               "nodes": [], "links": []}
    if mat.use_nodes:
        for node in sorted(mat.node_tree.nodes, key=lambda node: node.name):
            payload["nodes"].append({"name": node.name, "type": node.bl_idname,
                                    "inputs": [(socket.name, json_value(socket.default_value))
                                               for socket in node.inputs
                                               if hasattr(socket, "default_value")]})
        payload["links"] = sorted((link.from_node.name, link.from_socket.identifier,
                                   link.to_node.name, link.to_socket.identifier)
                                  for link in mat.node_tree.links)
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def object_snapshot(obj):
    entry = {"type": obj.type,
             "matrix_basis": [list(row) for row in obj.matrix_basis],
             "parent": obj.parent.name if obj.parent else None,
             "materials": [mat.name for mat in obj.data.materials] if obj.type == "MESH" else []}
    if obj.type == "LIGHT":
        entry["light"] = {key: json_value(getattr(obj.data, key)) for key in
                          ["type", "energy", "color", "shape", "size", "size_y"]}
    elif obj.type == "CAMERA":
        entry["camera"] = {key: json_value(getattr(obj.data, key)) for key in
                           ["lens", "type", "sensor_fit", "sensor_width", "sensor_height"]}
        entry["dof"] = {"enabled": obj.data.dof.use_dof,
                        "focus_object": obj.data.dof.focus_object.name if obj.data.dof.focus_object else None,
                        "focus_distance": obj.data.dof.focus_distance,
                        "fstop": obj.data.dof.aperture_fstop}
    return entry


def sphere_profile(z):
    r = math.sqrt(max(0.0, SPHERE_RADIUS ** 2 - (z + SPHERE_RADIUS) ** 2))
    return r, -(z + SPHERE_RADIUS) / r


TOP_RADIUS, TOP_DERIVATIVE = sphere_profile(BLEND_TOP)


def blended_profile(z):
    span = BLEND_TOP - BLEND_BOTTOM
    t = (z - BLEND_BOTTOM) / span
    r = ((2 * t ** 3 - 3 * t ** 2 + 1) * RADIUS
         + (-2 * t ** 3 + 3 * t ** 2) * TOP_RADIUS
         + (t ** 3 - t ** 2) * span * TOP_DERIVATIVE)
    drdz = (((6 * t ** 2 - 6 * t) * RADIUS
             + (-6 * t ** 2 + 6 * t) * TOP_RADIUS) / span
            + (3 * t ** 2 - 2 * t) * TOP_DERIVATIVE)
    return r, drdz


def pin_mesh(name):
    # Rings are ordered from the bottom to the top. Their analytic normals are
    # shared across the smooth surface, while the closed bottom stays flat.
    rings = [(SHAFT_BOTTOM, RADIUS, 0.0), (BLEND_BOTTOM, RADIUS, 0.0)]
    for k in range(1, BLEND_STEPS + 1):
        z = BLEND_BOTTOM + (BLEND_TOP - BLEND_BOTTOM) * k / BLEND_STEPS
        r, derivative = blended_profile(z)
        rings.append((z, r, derivative))
    start_angle = math.acos((BLEND_TOP + SPHERE_RADIUS) / SPHERE_RADIUS)
    for k in range(1, CAP_STEPS):
        angle = start_angle * (1 - k / CAP_STEPS)
        z = SPHERE_RADIUS * math.cos(angle) - SPHERE_RADIUS
        r = SPHERE_RADIUS * math.sin(angle)
        rings.append((z, r, -math.cos(angle) / math.sin(angle)))

    verts, normals, faces = [], [], []
    for z, r, derivative in rings:
        length = math.sqrt(1 + derivative * derivative)
        for sector in range(SECTORS):
            angle = 2 * math.pi * sector / SECTORS
            c, s = math.cos(angle), math.sin(angle)
            verts.append((r * c * MM, r * s * MM, z * MM))
            normals.append((c / length, s / length, -derivative / length))
    for ring in range(len(rings) - 1):
        for sector in range(SECTORS):
            nxt = (sector + 1) % SECTORS
            faces.append((ring * SECTORS + sector, ring * SECTORS + nxt,
                          (ring + 1) * SECTORS + nxt, (ring + 1) * SECTORS + sector))
    apex = len(verts)
    verts.append((0, 0, 0))
    normals.append((0, 0, 1))
    last = (len(rings) - 1) * SECTORS
    for sector in range(SECTORS):
        faces.append((last + sector, last + (sector + 1) % SECTORS, apex))
    flat_from = len(faces)
    centre = len(verts)
    verts.append((0, 0, SHAFT_BOTTOM * MM))
    normals.append((0, 0, -1))
    for sector in range(SECTORS):
        faces.append(((sector + 1) % SECTORS, sector, centre))
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    mesh.polygons.foreach_set("use_smooth", [True] * len(mesh.polygons))
    loop_normals = []
    for polygon in mesh.polygons:
        for vertex_index in polygon.vertices:
            loop_normals.append((0, 0, -1) if polygon.index >= flat_from else normals[vertex_index])
    mesh.normals_split_custom_set(loop_normals)
    mesh.update()
    return mesh


def verify_mesh(mesh):
    edge_faces = Counter()
    adjacency = {vertex.index: set() for vertex in mesh.vertices}
    volume = 0.0
    for polygon in mesh.polygons:
        indices = list(polygon.vertices)
        for a, b in zip(indices, indices[1:] + indices[:1]):
            edge_faces[tuple(sorted((a, b)))] += 1
            adjacency[a].add(b)
            adjacency[b].add(a)
        origin = mesh.vertices[indices[0]].co
        for j in range(1, len(indices) - 1):
            b = mesh.vertices[indices[j]].co
            c = mesh.vertices[indices[j + 1]].co
            volume += origin.dot(b.cross(c)) / 6
    assert all(count == 2 for count in edge_faces.values())
    unseen = set(adjacency)
    components = []
    while unseen:
        todo, count = [unseen.pop()], 0
        while todo:
            index = todo.pop()
            count += 1
            for other in adjacency[index]:
                if other in unseen:
                    unseen.remove(other)
                    todo.append(other)
        components.append(count)
    assert len(components) == 1
    assert volume > 0
    radii = [math.hypot(v.co.x, v.co.y) / MM for v in mesh.vertices]
    shaft_radii = [r for r, v in zip(radii, mesh.vertices)
                   if v.co.z / MM <= BLEND_BOTTOM + 1e-5 and r > .1]
    assert max(abs(r - RADIUS) for r in shaft_radii) < 1e-6
    crown_errors = []
    for vertex, r in zip(mesh.vertices, radii):
        z = vertex.co.z / MM
        if z >= BLEND_TOP - 1e-6:
            sphere_r = math.sqrt(max(0, SPHERE_RADIUS ** 2 - (z + SPHERE_RADIUS) ** 2))
            crown_errors.append(abs(r - sphere_r))
    assert max(crown_errors) < 1e-5
    return {"vertices": len(mesh.vertices), "faces": len(mesh.polygons),
            "connected_components": len(components), "watertight": True,
            "positive_volume_mm3": volume / MM ** 3,
            "diameter_mm": 2 * max(radii),
            "min_local_z_mm": min(v.co.z for v in mesh.vertices) / MM,
            "max_local_z_mm": max(v.co.z for v in mesh.vertices) / MM,
            "shaft_radius_max_error_mm": max(abs(r - RADIUS) for r in shaft_radii),
            "retained_crown_profile_max_error_mm": max(crown_errors)}


source_sha = file_hash(SOURCE)
bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
bpy.context.preferences.filepaths.save_version = 0
scene = bpy.context.scene
module = bpy.data.collections["MODULE - static assembly"]
parts = [obj for obj in module.objects if obj.type == "MESH"]
assert len(parts) == 22
source_objects = {obj.name: object_snapshot(obj) for obj in bpy.data.objects}
source_meshes = {obj.name: mesh_hash(obj.data) for obj in parts}
source_materials = {mat.name: material_hash(mat) for mat in bpy.data.materials}
source_camera = scene.camera.name
source_world = scene.world.name
source_frame = scene.frame_current
old_shader = bpy.data.objects["Dot_1"].data.materials[0]
shared_shader = old_shader.copy()
shared_shader.name = "Unified grey white tactile pin polymer"
shared_shader_name = shared_shader.name
shared_shader.diffuse_color = (*COLOUR, 1)
bsdf = shared_shader.node_tree.nodes.get("Principled BSDF")
assert bsdf is not None
bsdf.inputs["Base Color"].default_value = (*COLOUR, 1)
bsdf.inputs["Roughness"].default_value = ROUGHNESS
bsdf.inputs["Subsurface Weight"].default_value = SSS_WEIGHT
bsdf.inputs["Subsurface Scale"].default_value = SSS_SCALE_MM * MM
assert bsdf.inputs["Emission Strength"].default_value == 0

# Hsinlung wants the cap and shaft to read as one even grey-white pin, without
# the darker received-shadow band of the preceding photographic treatment.
# Limit that display treatment to the camera; secondary rays keep the polymer.
nodes = shared_shader.node_tree.nodes
links = shared_shader.node_tree.links
output_nodes = [node for node in nodes if node.type == "OUTPUT_MATERIAL"]
assert len(output_nodes) == 1
output_node = output_nodes[0]
display = nodes.new("ShaderNodeEmission")
display.name = "Uniform camera-facing grey-white pin"
display.label = "Uniform pin display colour"
display.inputs["Color"].default_value = (*DISPLAY_RGB, 1)
display.inputs["Strength"].default_value = 1.0
display_mix = nodes.new("ShaderNodeMixShader")
display_mix.name = "Subtle polymer detail in pin display"
display_mix.label = "12% physical highlight and surface detail"
display_mix.inputs[0].default_value = DISPLAY_PBR_MIX
links.new(display.outputs[0], display_mix.inputs[1])
links.new(bsdf.outputs["BSDF"], display_mix.inputs[2])
ray_type = nodes.new("ShaderNodeLightPath")
ray_type.name = "Camera-only uniform pin treatment"
camera_mix = nodes.new("ShaderNodeMixShader")
camera_mix.name = "Physical polymer for secondary rays"
links.new(ray_type.outputs["Is Camera Ray"], camera_mix.inputs[0])
links.new(bsdf.outputs["BSDF"], camera_mix.inputs[1])
links.new(display_mix.outputs[0], camera_mix.inputs[2])
links.new(camera_mix.outputs[0], output_node.inputs["Surface"])

dot_checks = {}
for number in range(1, 7):
    obj = bpy.data.objects[f"Dot_{number}"]
    old_mesh = obj.data
    obj.data = pin_mesh(f"Dot_{number}_ContinuousPin_Mesh")
    obj.data.materials.append(shared_shader)
    dot_checks[obj.name] = verify_mesh(obj.data)
    assert object_snapshot(obj)["matrix_basis"] == source_objects[obj.name]["matrix_basis"]
    assert obj.parent.name == source_objects[obj.name]["parent"]
    assert mesh_hash(obj.data) != source_meshes[obj.name]
    if old_mesh.users == 0:
        bpy.data.meshes.remove(old_mesh)

unchanged_meshes = []
for obj in parts:
    if not obj.name.startswith("Dot_"):
        assert mesh_hash(obj.data) == source_meshes[obj.name]
        unchanged_meshes.append(obj.name)
for obj in bpy.data.objects:
    if not obj.name.startswith("Dot_"):
        assert object_snapshot(obj) == source_objects[obj.name]
for name, expected in source_materials.items():
    assert material_hash(bpy.data.materials[name]) == expected
assert scene.camera.name == source_camera
assert scene.world.name == source_world
assert scene.frame_current == source_frame
assert not bpy.data.actions
assert len(unchanged_meshes) == 16

# Keep the scene retracted and preserve all camera, light and render settings.
bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT))
assert file_hash(SOURCE) == source_sha
bpy.ops.wm.open_mainfile(filepath=str(OUTPUT))
readback = {f"Dot_{i}": verify_mesh(bpy.data.objects[f"Dot_{i}"].data) for i in range(1, 7)}
assert len({bpy.data.objects[f"Dot_{i}"].data.materials[0].name for i in range(1, 7)}) == 1
assert all(set(p.material_index for p in bpy.data.objects[f"Dot_{i}"].data.polygons) == {0}
           for i in range(1, 7))
assert file_hash(SOURCE) == source_sha
payload = {
    "pass": True, "source": str(SOURCE), "source_sha256": source_sha,
    "source_file_unchanged": True, "output": str(OUTPUT),
    "intent": "Six continuous round-headed cylindrical pins, with one neutral grey-white polymer palette.",
    "changed_meshes": list(dot_checks), "unchanged_module_meshes": unchanged_meshes,
    "unchanged_mesh_count": len(unchanged_meshes),
    "all_object_transforms_and_dot_apices_unchanged": True,
    "other_materials_lights_cameras_world_and_render_settings_unchanged": True,
    "rest_state": "All six apices flush; no motion or animation added.",
    "profile_mm": {"shaft_radius": RADIUS, "shaft_bottom": SHAFT_BOTTOM,
                   "straight_shaft_top": BLEND_BOTTOM, "transition_top": BLEND_TOP,
                   "transition_continuity": "C1 tangent; analytic smooth normals",
                   "original_spherical_crown_retained_above": BLEND_TOP,
                   "crown_sphere_radius": SPHERE_RADIUS,
                   "apex": 0, "original_seam_radius_change": RADIUS - blended_profile(-.45)[0]},
    "shared_material": {"name": shared_shader_name, "base_colour_linear_rgb": COLOUR,
                        "roughness": ROUGHNESS, "subsurface_weight": SSS_WEIGHT,
                        "subsurface_scale_mm": SSS_SCALE_MM, "physical_shader_emission": 0,
                        "camera_display_linear_rgb": DISPLAY_RGB,
                        "camera_display_emission_strength": 1,
                        "camera_display_physical_shader_fraction": DISPLAY_PBR_MIX,
                        "secondary_rays": "Original physical polymer branch",
                        "intent": "Even grey-white cap and shaft with reduced received-shadow contrast; no added lighting."},
    "dot_geometry": readback,
    "verification_scope": "Geometry, palette assignment, preservation and saved-file readback. No render was produced."
}
REPORT.write_text(json.dumps(payload, indent=2), encoding="utf-8")
print(f"Saved {OUTPUT.name}. Six dot meshes changed; 16 module meshes and photographic setup preserved.", flush=True)
