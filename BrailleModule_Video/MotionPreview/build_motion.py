"""Add independent dot motion to the corrected appearance scene, without rendering.

Run with the project's Blender Python runtime. The corrected source stays untouched.
The browser preview owns keyboard controls; this file provides the editable rig and
a sample timeline. Heights and timing are visual prototype values.
"""
from pathlib import Path
import hashlib
import json
import struct

import bpy
from mathutils import Vector


HERE = Path(__file__).resolve().parent
SOURCE = HERE / "AppearanceStudy.blend"
OUTPUT = HERE / "ModuleMotion.blend"
REPORT = HERE / "RigVerification.json"
PROFILE = HERE / "assets" / "motion.json"
APPEARANCE_REPORT = HERE / "AppearanceVerification.json"
motion = json.loads(PROFILE.read_text(encoding="utf-8"))
MM = .001
PEAK_MM = float(motion["peak_mm"])
HOLD_MM = float(motion["hold_mm"])
FPS = 60
assert motion["curve"] == "linear"
RISE_FRAMES = round(float(motion["rise_ms"]) * FPS / 1000)
PEAK_FRAMES = round(float(motion["peak_pause_ms"]) * FPS / 1000)
SETTLE_FRAMES = round(float(motion["settle_ms"]) * FPS / 1000)
RETRACT_FRAMES = round(float(motion["retract_ms"]) * FPS / 1000)
assert all(duration > 0 for duration in [RISE_FRAMES, PEAK_FRAMES, SETTLE_FRAMES, RETRACT_FRAMES])
STARTS = {i: 1 + (i - 1) * 48 for i in range(1, 7)}
RETRACT_AT = 360
END_FRAME = 430


def sha_file(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def mesh_hash(obj):
    h = hashlib.sha256()
    for vertex in obj.data.vertices:
        h.update(struct.pack("<3f", *vertex.co))
    for polygon in obj.data.polygons:
        h.update(struct.pack("<II", len(polygon.vertices), polygon.material_index))
        for index in polygon.vertices:
            h.update(struct.pack("<I", index))
    return h.hexdigest()


def matrix_tuple(matrix):
    return tuple(tuple(row) for row in matrix)


def value_as_json(value):
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
                                    "inputs": [(socket.name, value_as_json(socket.default_value))
                                               for socket in node.inputs
                                               if hasattr(socket, "default_value")]})
        payload["links"] = sorted((link.from_node.name, link.from_socket.identifier,
                                   link.to_node.name, link.to_socket.identifier)
                                  for link in mat.node_tree.links)
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def object_snapshot(obj):
    entry = {"matrix_basis": matrix_tuple(obj.matrix_basis),
             "parent": obj.parent.name if obj.parent else None,
             "type": obj.type}
    if obj.type == "LIGHT":
        entry["light"] = {"type": obj.data.type, "energy": obj.data.energy,
                          "color": tuple(obj.data.color), "shape": obj.data.shape,
                          "size": obj.data.size, "size_y": obj.data.size_y}
    if obj.type == "CAMERA":
        entry["camera"] = {"lens": obj.data.lens, "type": obj.data.type,
                           "sensor_fit": obj.data.sensor_fit,
                           "sensor_width": obj.data.sensor_width,
                           "sensor_height": obj.data.sensor_height,
                           "dof": obj.data.dof.use_dof,
                           "focus": obj.data.dof.focus_object.name,
                           "fstop": obj.data.dof.aperture_fstop}
    return entry


appearance_report = json.loads(APPEARANCE_REPORT.read_text(encoding="utf-8"))
assert appearance_report["pass"]
assert Path(appearance_report["output"]).resolve() == SOURCE.resolve()
assert appearance_report["unchanged_mesh_count"] == 16
original_source = Path(appearance_report["source"])
assert sha_file(original_source) == appearance_report["source_sha256"]
bpy.ops.wm.open_mainfile(filepath=str(original_source))
original_static_meshes = {name: mesh_hash(bpy.data.objects[name])
                          for name in appearance_report["unchanged_module_meshes"]}
source_sha = sha_file(SOURCE)
bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
scene = bpy.context.scene
root = bpy.data.objects["BrailleModule"]
module = bpy.data.collections["MODULE - static assembly"]
parts = [obj for obj in module.objects if obj.type == "MESH"]
assert len(parts) == 22
assert not bpy.data.actions
source_meshes = {obj.name: mesh_hash(obj) for obj in parts}
assert all(source_meshes[name] == mesh for name, mesh in original_static_meshes.items())
source_objects = {obj.name: object_snapshot(obj) for obj in bpy.data.objects}
source_materials = {mat.name: material_hash(mat) for mat in bpy.data.materials}
rest_z = {i: bpy.data.objects[f"Dot_{i}"].location.z for i in range(1, 7)}

for i in range(1, 7):
    prop = f"Dot_{i}_height_mm"
    root[prop] = 0.0
    root.id_properties_ui(prop).update(
        min=0.0, max=PEAK_MM, soft_min=0.0, soft_max=PEAK_MM,
        description=f"Dot {i} height: 0 retracted, {PEAK_MM:.2f} peak, {HOLD_MM:.2f} maintained (mm)")
    dot = bpy.data.objects[f"Dot_{i}"]
    curve = dot.driver_add("location", 2)
    curve.driver.type = "SCRIPTED"
    variable = curve.driver.variables.new()
    variable.name = "height_mm"
    variable.type = "SINGLE_PROP"
    variable.targets[0].id = root
    variable.targets[0].data_path = f'["{prop}"]'
    curve.driver.expression = f"{rest_z[i]:.17g} + min(max(height_mm, 0.0), {PEAK_MM:.17g}) * 0.001"
    start = STARTS[i]
    keys = [(1, 0.0), (start, 0.0),
            (start + RISE_FRAMES, PEAK_MM),
            (start + RISE_FRAMES + PEAK_FRAMES, PEAK_MM),
            (start + RISE_FRAMES + PEAK_FRAMES + SETTLE_FRAMES, HOLD_MM),
            (RETRACT_AT, HOLD_MM), (RETRACT_AT + RETRACT_FRAMES, 0.0),
            (END_FRAME, 0.0)]
    for frame, height in sorted(set(keys)):
        root[prop] = height
        root.keyframe_insert(data_path=f'["{prop}"]', frame=frame, group=f"Dot {i}")

action = root.animation_data.action
action.name = "Six independent dots - rise, peak, maintained, retract"
for curve in action.fcurves:
    curve.extrapolation = "CONSTANT"
    for point in curve.keyframe_points:
        point.interpolation = "LINEAR"

scene.render.fps = FPS
scene.render.fps_base = 1.0
scene.frame_start = 1
scene.frame_end = END_FRAME
scene.camera = bpy.data.objects["Video closeup camera"]
scene.render.resolution_x = 1920
scene.render.resolution_y = 1080
scene.render.resolution_percentage = 100
scene.render.filepath = str(HERE / "ModuleMotion_Frame.png")
scene["Scope"] = "Accepted photographic scene with six independent vertical dot controls and a sample timeline."
scene["Dot_motion"] = f"0 mm retracted -> {PEAK_MM:.2f} mm peak -> {HOLD_MM:.2f} mm maintained; short linear transitions."
scene["Motion_values_are_provisional"] = True
scene["Motion_profile"] = "assets/motion.json"
scene["Motion_reference_basis"] = motion["basis"]
root["state"] = "Six independent height controls; reopen at frame 1 with all dots retracted."
root["motion_height_mm"] = [0.0, PEAK_MM, HOLD_MM]
root["motion_timing_ms"] = [motion["rise_ms"], motion["peak_pause_ms"], motion["settle_ms"], motion["retract_ms"]]
scene.timeline_markers.clear()
for i, start in STARTS.items():
    scene.timeline_markers.new(f"Dot {i} rise", frame=start)
scene.timeline_markers.new("All six maintained", frame=300)
scene.timeline_markers.new("Retract all six", frame=RETRACT_AT)
scene.timeline_markers.new("All six retracted", frame=RETRACT_AT + RETRACT_FRAMES)
scene.frame_set(1)
bpy.context.view_layer.update()
for obj in bpy.context.selected_objects:
    obj.select_set(False)
root.select_set(True)
bpy.context.view_layer.objects.active = root
for area in bpy.context.screen.areas:
    if area.type == "VIEW_3D":
        area.spaces.active.region_3d.view_perspective = "CAMERA"
    elif area.type == "PROPERTIES":
        area.spaces.active.context = "OBJECT"
bpy.context.preferences.filepaths.save_version = 0
bpy.ops.wm.save_as_mainfile(filepath=str(OUTPUT), compress=True)

# Reopen the actual deliverable and measure evaluated coordinates, not only keys.
bpy.ops.wm.open_mainfile(filepath=str(OUTPUT))
scene = bpy.context.scene
root = bpy.data.objects["BrailleModule"]
parts = [bpy.data.objects[name] for name in source_meshes]
assert all(mesh_hash(obj) == source_meshes[obj.name] for obj in parts)
assert {mat.name: material_hash(mat) for mat in bpy.data.materials} == source_materials
non_dots = [obj for obj in bpy.data.objects if not obj.name.startswith("Dot_")]
assert all(object_snapshot(obj) == source_objects[obj.name] for obj in non_dots)
assert scene.camera.name == "Video closeup camera"
assert scene.render.resolution_x == 1920 and scene.render.resolution_y == 1080
assert len(bpy.data.actions) == 1
assert all(point.interpolation == "LINEAR" for curve in root.animation_data.action.fcurves
           for point in curve.keyframe_points)

def measured_heights(frame):
    scene.frame_set(frame)
    bpy.context.view_layer.update()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    return [(bpy.data.objects[f"Dot_{i}"].evaluated_get(depsgraph).location.z - rest_z[i]) / MM
            for i in range(1, 7)]

EPS = 2e-5
samples = {"retracted": measured_heights(1), "maintained_all": measured_heights(300),
           "retracted_all": measured_heights(RETRACT_AT + RETRACT_FRAMES)}
assert all(abs(height) < EPS for height in samples["retracted"])
assert all(abs(height - HOLD_MM) < EPS for height in samples["maintained_all"])
assert all(abs(height) < EPS for height in samples["retracted_all"])
for i, start in STARTS.items():
    peak = measured_heights(start + RISE_FRAMES)
    hold = measured_heights(start + RISE_FRAMES + PEAK_FRAMES + SETTLE_FRAMES)
    rise_first_step = measured_heights(start + 1)
    settle_first_step = measured_heights(start + RISE_FRAMES + PEAK_FRAMES + 1)
    assert abs(peak[i - 1] - PEAK_MM) < EPS
    assert abs(hold[i - 1] - HOLD_MM) < EPS
    assert abs(rise_first_step[i - 1] - PEAK_MM / RISE_FRAMES) < EPS
    assert abs(settle_first_step[i - 1] - (PEAK_MM + (HOLD_MM - PEAK_MM) / SETTLE_FRAMES)) < EPS
    assert all(abs(peak[j] - HOLD_MM) < EPS for j in range(i - 1))
    assert all(abs(peak[j]) < EPS for j in range(i, 6))
    samples[f"dot_{i}_peak"] = peak
    samples[f"dot_{i}_maintained"] = hold
samples["retract_first_step"] = measured_heights(RETRACT_AT + 1)
assert all(abs(height - HOLD_MM * (1 - 1 / RETRACT_FRAMES)) < EPS
           for height in samples["retract_first_step"])
minimum = float("inf")
maximum = float("-inf")
for frame in range(1, END_FRAME + 1):
    values = measured_heights(frame)
    minimum = min(minimum, *values)
    maximum = max(maximum, *values)
    assert all(-EPS <= height <= PEAK_MM + EPS for height in values)
    assert all(object_snapshot(obj) == source_objects[obj.name] for obj in non_dots)

scene.frame_set(1)
bpy.context.view_layer.update()
assert all(object_snapshot(bpy.data.objects[f"Dot_{i}"]) == source_objects[f"Dot_{i}"] for i in range(1, 7))
# At full rise the original 0.85 mm hidden stem retains 0.15 mm below the face.
stem_depth = -min(vertex.co.z for vertex in bpy.data.objects["Dot_1"].data.vertices) / MM
peak_stem_overlap = stem_depth - PEAK_MM
assert peak_stem_overlap >= .14999
assert sha_file(SOURCE) == source_sha
report = {
    "source": str(SOURCE), "source_sha256": source_sha,
    "source_role": "Corrected round-cap cylindrical pins and unified grey-white appearance",
    "appearance_verification": str(APPEARANCE_REPORT),
    "appearance_verification_sha256": sha_file(APPEARANCE_REPORT),
    "original_static_meshes_verified_unchanged": len(original_static_meshes),
    "original_photographic_source": str(original_source),
    "original_photographic_source_sha256": appearance_report["source_sha256"],
    "output": str(OUTPUT), "saved_blend_reopened_and_verified": True,
    "unchanged_meshes": 22, "unchanged_materials": True,
    "unchanged_non_dot_transforms_lights_and_cameras": True,
    "frame_1_matches_all_original_part_transforms": True,
    "camera": scene.camera.name, "resolution": [1920, 1080],
    "root": root.name, "control_properties": [f"Dot_{i}_height_mm" for i in range(1, 7)],
    "prototype_heights_mm": {"retracted": 0.0, "peak": PEAK_MM, "maintained": HOLD_MM},
    "timings_ms_provisional": {"rise": motion["rise_ms"], "peak": motion["peak_pause_ms"],
                               "settle": motion["settle_ms"], "retract": motion["retract_ms"]},
    "motion_profile": str(PROFILE), "motion_profile_sha256": sha_file(PROFILE),
    "motion_profile_revision": motion["revision"], "curve": motion["curve"],
    "reference_basis": motion["basis"],
    "timeline": {"fps": FPS, "start": 1, "end": END_FRAME, "dot_starts": STARTS,
                 "rise_frames": RISE_FRAMES, "peak_frames": PEAK_FRAMES,
                 "settle_frames": SETTLE_FRAMES, "retract_at": RETRACT_AT,
                 "retract_frames": RETRACT_FRAMES},
    "sampled_height_range_mm": [minimum, maximum], "frames_measured": END_FRAME,
    "peak_stem_overlap_below_face_mm": peak_stem_overlap,
    "samples_measured_mm": samples,
    "no_compositor_filters_added": True, "no_wear_added": True,
    "no_renders_run_by_builder": True,
}
REPORT.write_text(json.dumps(report, indent=2), encoding="utf-8")
print(json.dumps({"saved": str(OUTPUT), "verified": 22, "controls": report["control_properties"],
                  "heights_mm": report["sampled_height_range_mm"]}))
