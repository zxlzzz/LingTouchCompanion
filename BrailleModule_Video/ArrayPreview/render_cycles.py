"""Cycles production pipeline. The browser remains the sequence editor.

Run with the retained bpy Python runtime. `stills` is the default; a full
sequence is rendered only with the explicit `render` command.
"""
import argparse
import hashlib
import json
import math
import shutil
import struct
import subprocess
from pathlib import Path

import bpy
import cv2
import numpy as np
from mathutils import Vector

ROOT = Path(__file__).resolve().parent
BLEND = ROOT / "EnclosedArray.blend"
ASSETS = ROOT / "assets"
TEXTURES = ASSETS / "textures"
SHOTS = ("near", "switch", "whole")
MM = 0.001


def parse_sequence(path):
    text = Path(path).read_text(encoding="utf-8-sig")
    try:
        value = json.loads(text)
    except json.JSONDecodeError:
        value = [json.loads(line) for line in text.splitlines() if line.strip()]
    if isinstance(value, dict):
        value = value.get("frames", [value])
    if (isinstance(value, list) and len(value) == 10
            and all(isinstance(row, list) and len(row) == 9
                    and all(isinstance(cell, (bool, int, float)) for cell in row)
                    for row in value)):
        value = [{"ts": 0, "frame": value}]
    if not isinstance(value, list) or not value or len(value) > 100000:
        raise ValueError("Expected 1 to 100000 frame records")
    records, previous = [], -math.inf
    for i, item in enumerate(value):
        grid = item["frame"]
        if len(grid) != 10 or any(len(row) != 9 for row in grid):
            raise ValueError(f"Record {i}: expected a 10 x 9 grid")
        if any(not isinstance(x, (int, float, bool)) or not math.isfinite(x)
               for row in grid for x in row):
            raise ValueError(f"Record {i}: non-finite or non-numeric cell")
        ts = item.get("ts", i * 500)
        if not isinstance(ts, (int, float)) or not math.isfinite(ts) or ts < 0 or ts < previous:
            raise ValueError(f"Record {i}: invalid or decreasing millisecond timestamp")
        previous = ts
        records.append({**item, "seq": item.get("seq", i), "ts": ts,
                        "frame": [[int(bool(x)) for x in row] for row in grid]})
    return records


def demo_sequence():
    empty = [[0] * 9 for _ in range(10)]
    patterns = [empty, [[int((r + c) % 2 == 0) for c in range(9)] for r in range(10)],
                [[int(c == 4 or r in (4, 5)) for c in range(9)] for r in range(10)],
                [[1] * 9 for _ in range(10)], empty]
    return [{"seq": i, "ts": i * 1000, "mode": "LOCAL_ZOOM", "frame": grid}
            for i, grid in enumerate(patterns)]


def grid_index(r, c):
    return (r // 2 * 3 + c // 3) * 6 + (r % 2) * 3 + 2 - c % 3


def at_time(keys, time):
    for (ta, a), (tb, b) in zip(keys, keys[1:]):
        if ta <= time < tb:
            return a + (b - a) * (time - ta) / (tb - ta)
    return keys[0][1] if time < keys[0][0] else keys[-1][1]


def dot_curve(events, motion):
    """Exact piecewise-linear browser motion, including interrupted strokes."""
    keys, target = [(0.0, 0.0)], False
    for time, next_target in events:
        next_target = bool(next_target)
        if next_target == target:
            continue
        height = at_time(keys, time)
        keys = [(t, h) for t, h in keys if t < time]
        keys.append((time, height))
        if next_target:
            rise = time + motion["rise_ms"]
            pause = rise + motion["peak_pause_ms"]
            end = pause + motion["settle_ms"]
            keys.extend([(rise, motion["peak_mm"]), (pause, motion["peak_mm"]),
                         (end, motion["hold_mm"])])
        else:
            keys.append((time + motion["retract_ms"], 0.0))
        target = next_target
        keys = list(dict(keys).items())  # same-time commands and zero-length pauses
    return sorted(keys)


def check_motion(motion):
    if not (0 < motion["hold_mm"] < motion["peak_mm"] <= 1):
        raise ValueError("Invalid pin heights")
    if (any(motion[k] <= 0 for k in ("rise_ms", "settle_ms", "retract_ms"))
            or motion["peak_pause_ms"] < 0 or motion["curve"] != "linear"):
        raise ValueError("Unsupported motion profile")
    # Compare to the actual browser function, including reversals mid-stroke.
    source = (ROOT / "controls.js").read_text(encoding="utf-8")
    function = source[source.index("  function updateMotion("):source.index("  function setTarget(")]
    cases = [[(0, 1), (400, 0)], [(0, 1), (14, 0), (29, 1), (90, 0), (91, 1)],
             [(0, 1), (0, 0), (0, 1), (50, 1), (100, 0), (110, 0), (125, 1)]]
    times = sorted(set([float(t) for t in range(0, 601, 7)] +
                       [t + x for case in cases for t, _ in case for x in (0, .01, 16.5, 33.333333, 50, 100, 150)]))
    js = "const motion=" + json.dumps(motion) + "; const clamp=v=>Math.max(0,Math.min(1,v));\n" + function
    js += "\nconst cases=" + json.dumps(cases) + ",times=" + json.dumps(times) + ";\n"
    js += """console.log(JSON.stringify(cases.map(events=>times.map(now=>{
      const state={target:false,height:0,phase:'idle',startHeight:0,started:0};
      for(const [t,target] of events){ if(t>now)break;
        if(state.target===Boolean(target))continue;
        updateMotion(state,t);state.startHeight=state.height;state.target=Boolean(target);
        state.started=t;state.phase=state.target?'rise':state.height>0?'retract':'idle';
      } updateMotion(state,now);return state.height;
    }))));"""
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Node is required to verify against browser motion")
    expected = json.loads(subprocess.run([node, "-e", js], check=True, capture_output=True, text=True).stdout)
    maximum = 0
    for case, values in zip(cases, expected):
        curve = dot_curve(case, motion)
        maximum = max(maximum, max(abs(at_time(curve, t) - h) for t, h in zip(times, values)))
    if maximum > 1e-7:
        raise AssertionError(f"Browser motion mismatch: {maximum} mm")
    return {"browser_comparison_samples": len(cases) * len(times), "max_error_mm": maximum}


def mesh_fingerprint(obj):
    digest = hashlib.sha256()
    for vertex in obj.data.vertices:
        digest.update(struct.pack("<3f", *vertex.co))
    for poly in obj.data.polygons:
        digest.update(struct.pack("<I", len(poly.vertices)))
        for index in poly.vertices:
            digest.update(struct.pack("<I", index))
    return digest.hexdigest()


def photo_texture():
    """Extract mould detail; remove holes and broad baked illumination."""
    TEXTURES.mkdir(exist_ok=True)
    photo = ROOT.parent / "inputs/Touchpoint_Reference.jpg"
    raw = cv2.imdecode(np.frombuffer(photo.read_bytes(), np.uint8), cv2.IMREAD_COLOR)
    corners = np.float32([[626, 285], [873, 623], [1094, 548], [867, 224]])
    matrix = cv2.getPerspectiveTransform(corners, np.float32([[0, 0], [819, 0], [819, 599], [0, 599]]))
    face = cv2.warpPerspective(raw, matrix, (820, 600))
    grey = cv2.cvtColor(face, cv2.COLOR_BGR2GRAY)
    # Pins and their rim shadows are not a material texture.
    mask = np.zeros_like(grey)
    for x, y in ((155, 151), (393, 129), (642, 122), (159, 409), (397, 405), (647, 397)):
        cv2.circle(mask, (x, y), 118, 255, -1)
    mask[:30] = mask[-30:] = 255
    mask[:, :30] = mask[:, -30:] = 255
    repaired = cv2.inpaint(grey, mask, 7, cv2.INPAINT_TELEA).astype(np.float32)
    detail = repaired - cv2.GaussianBlur(repaired, (0, 0), 13)
    detail = np.clip(detail / 22.0, -1, 1)
    # Seamless reflection about boundaries, limited photographic microvariation.
    detail = np.concatenate((detail, detail[:, ::-1]), axis=1)
    detail = np.concatenate((detail, detail[::-1]), axis=0)
    detail = cv2.resize(detail, (1024, 1024), interpolation=cv2.INTER_AREA)
    path = TEXTURES / "MouldDetail.png"
    cv2.imwrite(str(path), np.round((detail * .30 + .5) * 65535).astype(np.uint16))
    return {"source": "../inputs/Touchpoint_Reference.jpg", "source_sha256": hashlib.sha256(photo.read_bytes()).hexdigest(),
            "rectification_corners_px": corners.tolist(), "texture": "assets/textures/MouldDetail.png",
            "method": "Perspective correction, pin/rim masking, inpainting, broad-illumination removal; grayscale roughness and microscopic normal detail only"}


def reset_material(name, colour, roughness):
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    mat.node_tree.nodes.clear()
    shader = mat.node_tree.nodes.new("ShaderNodeBsdfPrincipled")
    output = mat.node_tree.nodes.new("ShaderNodeOutputMaterial")
    mat.node_tree.links.new(shader.outputs["BSDF"], output.inputs["Surface"])
    shader.inputs["Base Color"].default_value = (*colour, 1)
    shader.inputs["Roughness"].default_value = roughness
    shader.inputs["Metallic"].default_value = 0
    shader.inputs["IOR"].default_value = 1.48
    mat.diffuse_color = (*colour, 1)
    return mat, shader


def rounded_normal(mat, shader, radius, normal=None):
    node = mat.node_tree.nodes.new("ShaderNodeBevel")
    node.label = "Microscopic edge highlight"
    node.samples = 6
    node.inputs["Radius"].default_value = radius
    if normal:
        mat.node_tree.links.new(normal, node.inputs["Normal"])
    mat.node_tree.links.new(node.outputs["Normal"], shader.inputs["Normal"])


def module_materials():
    previous = bpy.data.images.get("MouldDetail.png")
    if previous:
        bpy.data.images.remove(previous)
    image = bpy.data.images.load(str(TEXTURES / "MouldDetail.png"), check_existing=True)
    image.colorspace_settings.name = "Non-Color"
    image.pack()
    names = ["Photographic black moulded broad face", "Photographic black moulded narrow face",
             "Photographic black tactile face with broken gloss", "Clean black moulded housing"]
    for name in names:
        top = "tactile face" in name
        mat, p = reset_material(name, (.008, .009, .010), .46 if top else .48)
        nt = mat.node_tree
        coord = nt.nodes.new("ShaderNodeTexCoord")
        mapping = nt.nodes.new("ShaderNodeMapping")
        mapping.inputs["Scale"].default_value = (1 / .0164, 1 / .012, 1 / .0164)
        nt.links.new(coord.outputs["Object"], mapping.inputs["Vector"])
        info = nt.nodes.new("ShaderNodeObjectInfo")
        offset = nt.nodes.new("ShaderNodeVectorMath")
        offset.operation = "ADD"
        nt.links.new(mapping.outputs["Vector"], offset.inputs[0])
        nt.links.new(info.outputs["Random"], offset.inputs[1])
        tex = nt.nodes.new("ShaderNodeTexImage")
        tex.image = image
        tex.interpolation = "Linear"
        tex.projection = "FLAT" if top else "BOX"
        tex.projection_blend = .12
        nt.links.new(offset.outputs["Vector"], tex.inputs["Vector"])
        rough = nt.nodes.new("ShaderNodeMapRange")
        rough.inputs["To Min"].default_value = .39 if top else .43
        rough.inputs["To Max"].default_value = .52 if top else .53
        nt.links.new(tex.outputs["Color"], rough.inputs["Value"])
        nt.links.new(rough.outputs["Result"], p.inputs["Roughness"])
        bump = nt.nodes.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value = .18
        bump.inputs["Distance"].default_value = .000002
        nt.links.new(tex.outputs["Color"], bump.inputs["Height"])
        rounded_normal(mat, p, .000035, bump.outputs["Normal"])
        p.inputs["Specular IOR Level"].default_value = .5
    # Whole pin uses physical dielectric response, including inside the hole.
    mat, p = reset_material("Photographic neutral grey-white complete pins", (.36, .39, .405), .27)
    p.inputs["Subsurface Weight"].default_value = .035
    p.inputs["Subsurface Scale"].default_value = .00012
    p.inputs["Subsurface Radius"].default_value = (.7, .7, .7)
    rounded_normal(mat, p, .000008)
    for obj in bpy.data.objects:
        if "_Dot_" in obj.name:
            obj.visible_shadow = True
    mat, p = reset_material("Web switch plastic", (.006, .0065, .007), .46)
    rounded_normal(mat, p, .00003)


def pla_material():
    mat, p = reset_material("Web enclosure ivory PLA", (.66, .645, .60), .53)
    nt = mat.node_tree
    N = nt.nodes.new
    coord = N("ShaderNodeTexCoord")
    split = N("ShaderNodeSeparateXYZ")
    nt.links.new(coord.outputs["Object"], split.inputs[0])
    geometry = N("ShaderNodeNewGeometry")
    normal = N("ShaderNodeSeparateXYZ")
    nt.links.new(geometry.outputs["True Normal"], normal.inputs[0])

    def calc(operation, a, b):
        node = N("ShaderNodeMath")
        node.operation = operation
        for i, value in enumerate((a, b)):
            if isinstance(value, (float, int)):
                node.inputs[i].default_value = value
            else:
                nt.links.new(value, node.inputs[i])
        return node.outputs[0]

    # Exact browser spacings and relief amplitudes, converted mm -> metres.
    side = calc("COSINE", calc("MULTIPLY", split.outputs["Z"], 2 * math.pi / .00020), 0)
    diagonal = calc("MULTIPLY", calc("ADD", split.outputs["X"], calc("MULTIPLY", split.outputs["Y"], -1)), .7071068)
    top = calc("COSINE", calc("MULTIPLY", diagonal, 2 * math.pi / .00042), 0)
    top_factor = N("ShaderNodeMapRange")
    top_factor.interpolation_type = "SMOOTHSTEP"
    top_factor.inputs["From Min"].default_value = .55
    top_factor.inputs["From Max"].default_value = .94
    nt.links.new(calc("ABSOLUTE", normal.outputs["Z"], 0), top_factor.inputs["Value"])
    side_h = calc("MULTIPLY", side, .0000035)
    top_h = calc("MULTIPLY", top, .0000014)
    mix = N("ShaderNodeMixRGB")
    nt.links.new(top_factor.outputs["Result"], mix.inputs[0])
    nt.links.new(side_h, mix.inputs[1])
    nt.links.new(top_h, mix.inputs[2])
    bump = N("ShaderNodeBump")
    bump.inputs["Strength"].default_value = 1
    bump.inputs["Distance"].default_value = 1
    nt.links.new(mix.outputs[0], bump.inputs["Height"])
    rounded_normal(mat, p, .00007, bump.outputs["Normal"])
    p.inputs["Subsurface Weight"].default_value = .045
    p.inputs["Subsurface Scale"].default_value = .00035
    p.inputs["Subsurface Radius"].default_value = (.8, .65, .45)
    p.inputs["Specular IOR Level"].default_value = .5
    mat["side_layer_mm"] = .20
    mat["top_road_mm"] = .42
    mat["side_relief_mm"] = .0035
    mat["top_relief_mm"] = .0014


def small_bevels():
    for obj in bpy.data.objects:
        if obj.type != "MESH":
            continue
        radius = .00006 if obj.name.endswith("_Housing") else .00018 if obj.name.startswith("Enclosure_") else None
        if radius:
            mod = obj.modifiers.get("Production small round") or obj.modifiers.new("Production small round", "BEVEL")
            mod.width = radius
            mod.segments = 3
            mod.limit_method = "ANGLE"
            mod.angle_limit = math.radians(35)
            mod.use_clamp_overlap = True
            mod.harden_normals = True
        obj.visible_shadow = True


def environment(scene):
    world = scene.world
    world.use_nodes = True
    nt = world.node_tree
    nt.nodes.clear()
    coord = nt.nodes.new("ShaderNodeTexCoord")
    mapping = nt.nodes.new("ShaderNodeMapping")
    mapping.inputs["Rotation"].default_value[2] = math.radians(115)
    env = nt.nodes.new("ShaderNodeTexEnvironment")
    path = Path(bpy.utils.system_resource("DATAFILES")) / "studiolights/world/interior.exr"
    env.image = bpy.data.images.load(str(path), check_existing=True)
    env.image.pack()
    bg = nt.nodes.new("ShaderNodeBackground")
    bg.inputs["Strength"].default_value = .65
    output = nt.nodes.new("ShaderNodeOutputWorld")
    nt.links.new(coord.outputs["Generated"], mapping.inputs["Vector"])
    nt.links.new(mapping.outputs["Vector"], env.inputs["Vector"])
    nt.links.new(env.outputs["Color"], bg.inputs["Color"])
    nt.links.new(bg.outputs[0], output.inputs[0])
    key = bpy.data.objects["Directional window"]
    key.location = Vector((-.11, -.025, .18))
    key.rotation_euler = (Vector((0, 0, .0545)) - key.location).to_track_quat("-Z", "Y").to_euler()
    key.data.energy = .22
    key.data.size = .12
    key.data.size_y = .16
    key.data.color = (1, .965, .92)
    bpy.data.objects["Weak cool room bounce"].hide_render = True
    mat, p = reset_material("Warm pale laminate tabletop", (.115, .12, .12), .72)
    bpy.data.objects["Tabletop"].scale = (6, 6, 1)
    # Quiet tabletop; all occlusion comes from path tracing.
    return {"image": "Blender bundled interior.exr", "image_size": list(env.image.size),
            "packed": True, "rotation_degrees": 115, "strength": .65}


def animate(scene, records, motion, fps, tail):
    scene.render.fps = fps
    scene.render.fps_base = 1
    first_ts = records[0]["ts"]
    curves = {}
    for r in range(10):
        for c in range(9):
            index = grid_index(r, c)
            name = f"M{index // 6 + 1:02d}_Dot_{index % 6 + 1}"
            obj = bpy.data.objects[name]
            base = obj.get("production_rest_location")
            if base is None:
                base = list(obj.location)
                obj["production_rest_location"] = base
            obj.animation_data_clear()
            keys = dot_curve([(item["ts"] - first_ts, item["frame"][r][c]) for item in records], motion)
            curves[name] = keys
            axis = obj.parent.matrix_world.inverted().to_3x3() @ Vector((0, 0, 1))
            obj["grid_row"] = r
            obj["grid_column"] = c
            for time, height in keys:
                obj.location = Vector(base) + axis * height * MM
                obj.keyframe_insert(data_path="location", frame=1 + time * fps / 1000, group="Physical dot travel")
            action = obj.animation_data.action
            for curve in action.fcurves:
                curve.extrapolation = "CONSTANT"
                for key in curve.keyframe_points:
                    key.interpolation = "LINEAR"
    end_ms = max(records[-1]["ts"] - first_ts + tail * 1000,
                 max(keys[-1][0] for keys in curves.values()))
    scene.frame_start = 1
    scene.frame_end = math.ceil(end_ms * fps / 1000)
    for marker in list(scene.timeline_markers):
        scene.timeline_markers.remove(marker)
    for item in records:
        scene.timeline_markers.new(f"JSON seq {item['seq']}", frame=round(1 + (item["ts"] - first_ts) * fps / 1000))
    scene["Production_sequence"] = json.dumps(records)
    scene["Production_motion"] = json.dumps(motion)
    scene["Production_tail_seconds"] = tail
    scene.frame_set(1)
    return curves


def camera_pose(scene, shot):
    """Same axis transform, horizontal FOV and bounds-fitting as viewer3d.js."""
    def xyz(v):
        return Vector((v[0], -v[2], v[1])) * MM
    fov = math.radians(36.243)
    aspect = scene.render.resolution_x / scene.render.resolution_y
    if shot == "switch":
        target = xyz((0, 54.5, 19.5))
        position = target + xyz((6, 19, 10))
    else:
        if shot == "near":
            low, high, direction, margin = (-17, 52, -18), (17, 56, 23), (.15, 1.2, .80), 1.05
        else:
            bpy.context.view_layer.update()
            # Browser whole-view bounds are the model, without camera/lights/table.
            points = [obj.matrix_world @ Vector(v) for obj in bpy.data.objects
                      if obj.type == "MESH" and obj.name != "Tabletop" for v in obj.bound_box]
            lows = [min(p[i] for p in points) for i in range(3)]
            highs = [max(p[i] for p in points) for i in range(3)]
            low = (lows[0] / MM, lows[2] / MM, -highs[1] / MM)
            high = (highs[0] / MM, highs[2] / MM, -lows[1] / MM)
            direction, margin = (.85, 1.3, .80), 1.12
        corners = [xyz((x, y, z)) for x in (low[0], high[0]) for y in (low[1], high[1]) for z in (low[2], high[2])]
        target = (xyz(low) + xyz(high)) / 2
        direction = xyz(direction).normalized()
        right = (-direction).cross(Vector((0, 0, 1))).normalized()
        up = right.cross(-direction).normalized()
        horizontal = math.tan(fov / 2)
        vertical = horizontal / aspect
        distance = max((p - target).dot(direction) + max(abs((p - target).dot(right)) / horizontal,
                       abs((p - target).dot(up)) / vertical) for p in corners) * margin
        position = target + direction * distance
    return position, target


def cameras(scene):
    old_camera = scene.camera
    for shot in SHOTS:
        name = "Production camera " + shot
        obj = bpy.data.objects.get(name)
        if not obj:
            obj = bpy.data.objects.new(name, bpy.data.cameras.new(name))
            scene.collection.objects.link(obj)
        obj.animation_data_clear()
        obj.location, target = camera_pose(scene, shot)
        obj.rotation_euler = (target - obj.location).to_track_quat("-Z", "Y").to_euler()
        obj.data.type = "PERSP"
        obj.data.sensor_fit = "HORIZONTAL"
        obj.data.sensor_width = 36
        obj.data.lens = 36 / (2 * math.tan(math.radians(36.243) / 2))
        obj.data.clip_start = .0001
        obj.data.clip_end = 10
        focus = bpy.data.objects.get("Production focus " + shot)
        if not focus:
            focus = bpy.data.objects.new("Production focus " + shot, None)
            scene.collection.objects.link(focus)
        focus.location = target + Vector((0, 0, .00105)) if shot == "switch" else target
        focus.hide_render = True
        obj.data.dof.use_dof = True
        obj.data.dof.focus_object = focus
        obj.data.dof.aperture_fstop = {"near": 22, "switch": 32, "whole": 8}[shot]
        obj.data.dof.aperture_blades = 7
    scene.camera = bpy.data.objects["Production camera near"]
    if old_camera and old_camera.name == "Array photographic camera":
        bpy.data.objects.remove(old_camera, do_unlink=True)


def render_settings(scene, width, height, samples):
    scene.render.engine = "CYCLES"
    scene.render.resolution_x = width
    scene.render.resolution_y = height
    scene.render.resolution_percentage = 100
    scene.cycles.samples = samples
    scene.cycles.use_adaptive_sampling = True
    scene.cycles.adaptive_threshold = .012
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 10
    scene.cycles.diffuse_bounces = 4
    scene.cycles.glossy_bounces = 4
    scene.cycles.transparent_max_bounces = 8
    scene.render.use_motion_blur = True
    scene.render.motion_blur_shutter = .5
    scene.render.film_transparent = False
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.image_settings.color_depth = "16"
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -.35
    scene.render.use_compositing = False
    pref = bpy.context.preferences.addons["cycles"].preferences
    try:
        pref.compute_device_type = "OPTIX"
        pref.get_devices()
    except (TypeError, RuntimeError):
        pass
    gpu = [d for d in pref.devices if d.type == "OPTIX"]
    for d in pref.devices:
        d.use = d in gpu
    scene.cycles.device = "GPU" if gpu else "CPU"
    scene.cycles.use_persistent_data = True


def verify(scene):
    records = json.loads(scene["Production_sequence"])
    motion = json.loads(scene["Production_motion"])
    motion_checks = check_motion(motion)
    original_frame, subframe = scene.frame_current, scene.frame_subframe
    times = sorted(set([0, 16.666667, 33.333333, 100, 125, 150] +
                       [item["ts"] - records[0]["ts"] + dt for item in records
                        for dt in (0, 16.666667, 33.333333, 100, 125, 150, 175)]))
    maximum, count = 0, 0
    for r in range(10):
        for c in range(9):
            index = grid_index(r, c)
            obj = bpy.data.objects[f"M{index // 6 + 1:02d}_Dot_{index % 6 + 1}"]
            keys = dot_curve([(item["ts"] - records[0]["ts"], item["frame"][r][c]) for item in records], motion)
            if not obj.animation_data or not obj.animation_data.action:
                raise AssertionError(f"No animation on {obj.name}")
            curve = next(fc for fc in obj.animation_data.action.fcurves if fc.data_path == "location" and fc.array_index == 2)
            base = obj["production_rest_location"][2]
            for time in times:
                actual = (curve.evaluate(1 + time * scene.render.fps / 1000) - base) / MM
                maximum = max(maximum, abs(actual - at_time(keys, time)))
                count += 1
    if maximum > .00002:
        raise AssertionError(f"Baked keyframe error: {maximum} mm")
    # A geometric grid check prevents mirroring or a module-number permutation.
    bpy.context.view_layer.update()
    for r in range(10):
        row = [bpy.data.objects[f"M{grid_index(r,c)//6+1:02d}_Dot_{grid_index(r,c)%6+1}"] for c in range(9)]
        if any(a.matrix_world.translation.x >= b.matrix_world.translation.x for a, b in zip(row, row[1:])):
            raise AssertionError("Grid is mirrored or module columns are reordered")
    scene.frame_set(original_frame, subframe=subframe)
    return {"independent_animated_dots": 90, "baked_comparison_samples": count, "max_baked_error_mm": maximum,
            "grid_left_to_right_checked": True, **motion_checks}


def prepare(args):
    bpy.ops.wm.open_mainfile(filepath=str(BLEND))
    scene = bpy.context.scene
    before = {obj.name: mesh_fingerprint(obj) for obj in bpy.data.objects if obj.type == "MESH"}
    if args.sequence:
        records = parse_sequence(args.sequence)
        sequence_source = str(Path(args.sequence).resolve())
    elif (ASSETS / "sequence.json").exists():
        records = parse_sequence(ASSETS / "sequence.json")
        sequence_source = "assets/sequence.json"
    else:
        records = demo_sequence()
        sequence_source = "Browser built-in demo (appearance approval only)"
    (ASSETS / "sequence.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
    motion = json.loads((ASSETS / "motion.json").read_text(encoding="utf-8"))
    check_motion(motion)
    photo = photo_texture()
    module_materials()
    pla_material()
    small_bevels()
    env = environment(scene)
    animate(scene, records, motion, args.fps, args.tail)
    render_settings(scene, args.width, args.height, args.samples)
    cameras(scene)
    checks = verify(scene)
    after = {obj.name: mesh_fingerprint(obj) for obj in bpy.data.objects if obj.type == "MESH"}
    if before != after:
        raise AssertionError("Original mesh vertices or topology changed")
    # Retain source geometry and assembly placements; only dot travel is animated.
    scene["Production_sequence_source"] = sequence_source
    scene["Production_pipeline"] = "Cycles PNG sequence -> compositor grain -> Blender FFmpeg H.264 video"
    scene["Production_approval"] = "Still review pending; animation rendering requires explicit render command"
    scene["Production_reference"] = json.dumps(photo)
    scene["Production_mesh_fingerprints"] = json.dumps(after)
    scene.frame_set(1 + round(1.5 * args.fps))
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(BLEND), check_existing=False)
    web_path = ASSETS / "scene.json"
    web = json.loads(web_path.read_text(encoding="utf-8"))
    if "source_sha256" in web:
        web["model_export_source_sha256"] = web.pop("source_sha256")
    web.pop("blender_source_unchanged", None)
    web["production_scene"] = "EnclosedArray.blend"
    web["production_scene_sha256"] = hashlib.sha256(BLEND.read_bytes()).hexdigest()
    web["browser_role"] = "Sequence editing and interactive preview; final pictures and video use Cycles"
    web_path.write_text(json.dumps(web, ensure_ascii=False, indent=2), encoding="utf-8")
    report = {"engine": "CYCLES", "device": scene.cycles.device, "mesh_count": len(after),
              "original_mesh_geometry_preserved": True, "photo_texture": photo, "environment": env,
              "sequence_source": sequence_source, "input_records": len(records), "fps": args.fps,
              "frame_start": scene.frame_start, "frame_end": scene.frame_end,
              "motion": motion, "animation": checks, "preview_frame": scene.frame_current,
              "cameras": {shot: {"position_m": list(bpy.data.objects['Production camera '+shot].location),
                                  "fstop": bpy.data.objects['Production camera '+shot].data.dof.aperture_fstop,
                                  "source": "viewer3d.js setView + frameBounds"} for shot in SHOTS},
              "motion_blur_shutter_frames": .5, "full_sequence_rendered": False,
              "approval": "Await Hsinlung's still review before rendering sequences"}
    (ROOT / "CyclesVerification.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Prepared existing EnclosedArray.blend; 90 independent animations verified.", flush=True)


def load(args):
    bpy.ops.wm.open_mainfile(filepath=str(BLEND))
    scene = bpy.context.scene
    if "Production_sequence" not in scene:
        raise RuntimeError("Run prepare or stills before rendering")
    render_settings(scene, args.width, args.height, args.samples)
    cameras(scene)
    return scene


def grain_still(path):
    pixels = cv2.imread(str(path), cv2.IMREAD_UNCHANGED)
    rng = np.random.default_rng(31)
    scale = 65535 if pixels.dtype == np.uint16 else 255
    noise = rng.normal(0, .65 / 255 * scale, (*pixels.shape[:2], 1))
    pixels = np.clip(pixels.astype(np.float32) + noise, 0, scale).astype(pixels.dtype)
    cv2.imwrite(str(path), pixels)


def stills(args):
    prepare(args)
    scene = bpy.context.scene
    selected = SHOTS if args.shot == "all" else (args.shot,)
    frame = args.frame if args.frame is not None else scene.frame_current
    scene.frame_set(frame)
    for shot in selected:
        scene.camera = bpy.data.objects["Production camera " + shot]
        path = ROOT / {"near": "PinCloseup.png", "switch": "SwitchPreview.png", "whole": "EnclosureOverview.png"}[shot]
        scene.render.filepath = str(path)
        print(f"Still {shot}, frame {frame}, {args.width} x {args.height}, {args.samples} samples", flush=True)
        bpy.ops.render.render(write_still=True)
        grain_still(path)
    report_path = ROOT / "CyclesVerification.json"
    report = json.loads(report_path.read_text(encoding="utf-8"))
    report["stills"] = {"width": args.width, "height": args.height, "samples": args.samples,
                        "frame": frame, "grain_sigma_display_levels": .65,
                        "files": [str(ROOT / {"near": "PinCloseup.png", "switch": "SwitchPreview.png", "whole": "EnclosureOverview.png"}[shot]) for shot in selected]}
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Still review ready. No video sequence rendered.", flush=True)


def render_sequence(args):
    scene = load(args)
    # An explicit command is the only entry point to expensive whole-shot rendering.
    for shot in SHOTS if args.shot == "all" else (args.shot,):
        destination = ROOT / "frames" / shot
        destination.mkdir(parents=True, exist_ok=True)
        scene.camera = bpy.data.objects["Production camera " + shot]
        scene.render.filepath = str(destination / "frame_")
        print(f"Rendering {shot}: {scene.frame_start}..{scene.frame_end}", flush=True)
        bpy.ops.render.render(animation=True)


def compose(args):
    bpy.ops.wm.open_mainfile(filepath=str(BLEND))
    scene = bpy.context.scene
    for shot in SHOTS if args.shot == "all" else (args.shot,):
        destination = ROOT / "frames" / shot
        missing = [frame for frame in range(scene.frame_start, scene.frame_end + 1)
                   if not (destination / f"frame_{frame:04d}.png").exists()]
        if missing:
            raise RuntimeError(f"{shot}: {len(missing)} PNGs missing; video not composed")
        if args.ffmpeg:
            subprocess.run([args.ffmpeg, "-hide_banner", "-loglevel", "warning", "-y", "-framerate", str(scene.render.fps),
                            "-start_number", str(scene.frame_start), "-i", str(destination / "frame_%04d.png"),
                            "-vf", "format=yuv420p,noise=c0s=2:c0f=t+u:c1s=0:c2s=0:all_seed=31",
                            "-c:v", "libx264", "-crf", "17", "-preset", "slow", "-movflags", "+faststart",
                            str(ROOT / f"Array_{shot}.mp4")], check=True)
        else:
            compose_builtin([destination / f"frame_{frame:04d}.png"
                             for frame in range(scene.frame_start, scene.frame_end + 1)],
                            ROOT / f"Array_{shot}.mp4", scene.render.fps)


def compose_builtin(paths, output, fps):
    """Image-sequence compositor and bundled FFmpeg; original PNGs are retained."""
    if not bpy.app.build_options.codec_ffmpeg:
        raise RuntimeError("This Blender build has no FFmpeg encoder")
    first = cv2.imread(str(paths[0]), cv2.IMREAD_UNCHANGED)
    height, width = first.shape[:2]
    scene = bpy.data.scenes.new("PNG sequence composition")
    image = bpy.data.images.load(str(paths[0]), check_existing=False)
    image.source = "SEQUENCE"
    grain = bpy.data.textures.new("Fine monochrome film grain", "CLOUDS")
    grain.noise_scale = .001
    grain.noise_depth = 0
    camera = bpy.data.objects.new("Composition dummy camera", bpy.data.cameras.new("Composition dummy camera"))
    scene.collection.objects.link(camera)
    scene.camera = camera
    scene.render.engine = "CYCLES"
    scene.cycles.samples = 1
    scene.cycles.device = "CPU"
    scene.render.threads_mode = "FIXED"
    scene.render.threads = 2
    scene.render.resolution_x, scene.render.resolution_y = width, height
    scene.render.resolution_percentage = 100
    scene.render.fps = fps
    scene.render.fps_base = 1
    scene.frame_start, scene.frame_end = 1, len(paths)
    scene.use_nodes = True
    scene.node_tree.nodes.clear()
    source = scene.node_tree.nodes.new("CompositorNodeImage")
    source.image = image
    source.frame_start = 1
    source.frame_duration = len(paths)
    source.use_auto_refresh = True
    grain_node = scene.node_tree.nodes.new("CompositorNodeTexture")
    grain_node.texture = grain
    grain_node.inputs["Offset"].default_value = (0, 0, 0)
    grain_node.inputs["Offset"].keyframe_insert(data_path="default_value", frame=1)
    grain_node.inputs["Offset"].default_value = (len(paths) * .17, 0, len(paths) * .093)
    grain_node.inputs["Offset"].keyframe_insert(data_path="default_value", frame=max(2, len(paths)))
    subtract = scene.node_tree.nodes.new("CompositorNodeMath")
    subtract.operation = "SUBTRACT"
    subtract.inputs[1].default_value = .5
    scene.node_tree.links.new(grain_node.outputs["Value"], subtract.inputs[0])
    gamma_in = scene.node_tree.nodes.new("CompositorNodeGamma")
    gamma_in.inputs["Gamma"].default_value = 1 / 2.2
    scene.node_tree.links.new(source.outputs["Image"], gamma_in.inputs["Image"])
    mix = scene.node_tree.nodes.new("CompositorNodeMixRGB")
    mix.blend_type = "ADD"
    mix.inputs[0].default_value = .016
    scene.node_tree.links.new(gamma_in.outputs["Image"], mix.inputs[1])
    scene.node_tree.links.new(subtract.outputs[0], mix.inputs[2])
    gamma_out = scene.node_tree.nodes.new("CompositorNodeGamma")
    gamma_out.inputs["Gamma"].default_value = 2.2
    scene.node_tree.links.new(mix.outputs[0], gamma_out.inputs["Image"])
    composite = scene.node_tree.nodes.new("CompositorNodeComposite")
    scene.node_tree.links.new(gamma_out.outputs["Image"], composite.inputs["Image"])
    scene.render.use_compositing = True
    scene.render.use_sequencer = False
    scene.view_settings.view_transform = "Standard"
    scene.view_settings.look = "None"
    scene.view_settings.exposure = 0
    scene.view_settings.gamma = 1
    scene.render.image_settings.file_format = "FFMPEG"
    scene.render.ffmpeg.format = "MPEG4"
    scene.render.ffmpeg.codec = "H264"
    scene.render.ffmpeg.constant_rate_factor = "HIGH"
    scene.render.ffmpeg.ffmpeg_preset = "GOOD"
    scene.render.ffmpeg.gopsize = fps
    scene.render.filepath = str(output)

    window = bpy.context.window
    previous_scene = window.scene if window else None
    try:
        if window:
            window.scene = scene
        scene.frame_set(1)
        with bpy.context.temp_override(scene=scene):
            bpy.ops.render.render(animation=True, scene=scene.name)
    finally:
        if window:
            window.scene = previous_scene
        bpy.data.scenes.remove(scene)
        bpy.data.objects.remove(camera, do_unlink=True)
        bpy.data.images.remove(image)
        bpy.data.textures.remove(grain)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", nargs="?", default="stills", choices=("prepare", "stills", "render", "compose", "verify"))
    parser.add_argument("--sequence", help="Browser-exported JSON/JSONL; copied to assets/sequence.json")
    parser.add_argument("--shot", choices=(*SHOTS, "all"), default="all")
    parser.add_argument("--width", type=int, default=1920)
    parser.add_argument("--height", type=int, default=1080)
    parser.add_argument("--samples", type=int, default=192)
    parser.add_argument("--fps", type=int, default=30)
    parser.add_argument("--tail", type=float, default=1)
    parser.add_argument("--frame", type=int)
    parser.add_argument("--ffmpeg")
    args = parser.parse_args()
    if min(args.width, args.height, args.samples, args.fps) <= 0 or args.tail < 0:
        parser.error("Render dimensions, samples and fps must be positive; tail must be nonnegative")
    if args.command == "prepare":
        prepare(args)
    elif args.command == "stills":
        stills(args)
    elif args.command == "render":
        render_sequence(args)
    elif args.command == "compose":
        compose(args)
    else:
        scene = load(args)
        print(json.dumps(verify(scene), indent=2))


if __name__ == "__main__":
    main()
