"""Render the delivered meshes; produce unretouched WOAD comparison plates.

Run using the bundled Blender Python environment, for example:
  python render.py --samples 96
All coordinates and all renders are in the delivered wearing frame (mm).
This file creates no replacement geometry and applies no shape modifiers.
"""
from pathlib import Path
import argparse
import hashlib
import io
import json
import math
import sys

import numpy as np
import bpy
from mathutils import Vector
from PIL import Image, ImageDraw, ImageFont

P = Path(__file__).resolve().parent
G = P / "geometry"
W = P / "views"
R = P / "reference"
PREVIOUS = P.parent / "Headset_Carbon6K_FlatBase_Review_2026-10-02"
for d in (W, R):
    d.mkdir(parents=True, exist_ok=True)

parser = argparse.ArgumentParser()
parser.add_argument("--samples", type=int, default=96)
parser.add_argument("--width", type=int, default=1800)
parser.add_argument("--only", nargs="*", default=None)
parser.add_argument("--engine", choices=("CYCLES", "BLENDER_EEVEE_NEXT"), default="CYCLES")
parser.add_argument("--no-comparison", action="store_true")
args = parser.parse_args(sys.argv[1:])

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = args.engine
scene.render.resolution_percentage = 100
scene.render.image_settings.file_format = "PNG"
scene.render.image_settings.color_mode = "RGBA"
scene.render.film_transparent = True
if args.engine == "CYCLES":
    scene.cycles.samples = args.samples
    scene.cycles.use_denoising = True
    scene.cycles.device = "CPU"
scene.view_settings.view_transform = "AgX"
scene.view_settings.look = "AgX - Medium High Contrast"
scene.view_settings.exposure = 0
world = bpy.data.worlds.new("studio_environment")
scene.world = world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (.82, .85, .9, 1)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = .55

def material(name, color, roughness, metallic=0, specular=.4):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value = (*color, 1)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    bsdf.inputs["Specular IOR Level"].default_value = specular
    return mat

mats = {
    "shell": material("black satin printed shell", (.026, .029, .034), .30),
    "camera": material("camera polymer", (.034, .036, .040), .43),
    "lens": material("real optical surface", (.018, .035, .055), .075, .15),
    "metal": material("camera metal parts", (.29, .31, .33), .28, .75),
    "strap": material("blue webbing", (.075, .24, .48), .76),
    "head": material("neutral headform", (.57, .61, .62), .73),
    "battery": material("battery reference", (.12, .15, .17), .48),
    "pad": material("removable pad reference", (.20, .23, .25), .85),
}
glass = material("actual camera cover glass", (.94, .96, .99), .045, specular=.45)
glass.node_tree.nodes["Principled BSDF"].inputs["Transmission Weight"].default_value = 1
glass.node_tree.nodes["Principled BSDF"].inputs["IOR"].default_value = 1.45
mats["camera_glass"] = glass

# A restrained fabric shader affects only the already-delivered strap surfaces.
# It supplies material texture, with no displacement or silhouette alteration.
strap_nodes = mats["strap"].node_tree.nodes
strap_links = mats["strap"].node_tree.links
tex = strap_nodes.new("ShaderNodeTexNoise")
tex.inputs["Scale"].default_value = 4.0
tex.inputs["Detail"].default_value = 2.0
bump = strap_nodes.new("ShaderNodeBump")
bump.inputs["Strength"].default_value = .14
bump.inputs["Distance"].default_value = .035
strap_links.new(tex.outputs["Fac"], bump.inputs["Height"])
strap_links.new(bump.outputs["Normal"], strap_nodes.get("Principled BSDF").inputs["Normal"])

objects = {}
arrays = {}
mesh_has_parts = {}
source_hashes = {}
context_hashes = {}
rendered_views = []

def mesh(name, path, material_name, optional=False):
    if not path.exists():
        if optional:
            return None
        raise FileNotFoundError(path)
    raw = path.read_bytes()
    a = np.load(io.BytesIO(raw))
    v = np.asarray(a["v"], dtype=float)
    f = np.asarray(a["f"], dtype=np.int32)
    me = bpy.data.meshes.new(name)
    me.from_pydata(v.tolist(), [], f.tolist())
    me.update()
    ob = bpy.data.objects.new(name, me)
    scene.collection.objects.link(ob)
    ob.data.materials.append(mats[material_name])
    # Interpolate normals on genuine curved surfaces; preserve hard angles.
    # No subdivision, smoothing modifier, bevel, or other shape change.
    for poly in me.polygons:
        poly.use_smooth = True
    me.set_sharp_from_angle(angle=math.radians(32))
    # Boolean triangulation can span a large planar panel between ports. Its
    # normal must remain the exact plane normal: interpolating neighbouring
    # port-wall normals over those triangles invents a rectangular depression.
    # Curved loft and optical flare faces retain their smooth normals.
    if name in {"front", "service_lid"}:
        triangles = v[f]
        planar_y = np.ptp(triangles[:, :, 1], axis=1) < 1e-7
        for poly, is_planar in zip(me.polygons, planar_y):
            if is_planar:
                poly.use_smooth = False
    objects[name] = ob
    arrays[name] = v
    mesh_has_parts[name] = "part" in a.files
    source_hashes[name] = {
        "path": str(path.relative_to(P.parent)).replace("\\", "/"),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "vertices": len(v), "faces": len(f),
    }
    if material_name == "camera" and "part" in a.files:
        mapping = {}
        mp = G / "camera_materials.json"
        if mp.exists():
            material_bytes = mp.read_bytes()
            mapping = json.loads(material_bytes.decode("utf-8"))
            context_hashes["camera_materials.json"] = hashlib.sha256(material_bytes).hexdigest()
        for mn in ("lens", "metal", "camera_glass"):
            me.materials.append(mats[mn])
        indices = {"camera": 0, "lens": 1, "metal": 2, "camera_glass": 3}
        for poly, part in zip(me.polygons, a["part"]):
            poly.material_index = indices.get(mapping.get(str(int(part)), "camera"), 0)
    return ob

mesh("front", G / "front_body.npz", "shell")
mesh("service_lid", G / "service_lid.npz", "shell", optional=True)
mesh("camera", G / "camera.npz", "camera")
# A full physical camera already includes its optical assemblies. Rendering a
# second copy of those faces would create z-fighting and incorrect visibility.
if not mesh_has_parts["camera"]:
    mesh("camera_optics", G / "camera_optics.npz", "lens", optional=True)
mesh("fasteners", G / "fasteners.npz", "metal", optional=True)
mesh("pads", G / "pads.npz", "pad", optional=True)
mesh("cable_gland", G / "cable_gland.npz", "shell", optional=True)
mesh("rear", PREVIOUS / "geometry/rear_unified_preview.npz", "shell")
mesh("battery", PREVIOUS / "geometry/battery_preview.npz", "battery")
strap_path = G / "straps_preview.npz"
if not strap_path.exists():
    strap_path = PREVIOUS / "geometry/straps_preview.npz"
mesh("straps", strap_path, "strap")
mesh("head", PREVIOUS / "inputs/Medium_Trial_Registered.npz", "head")

# Optional delivered parts are declared here rather than invented for the view.
manifest_path = G / "render_manifest.json"
if manifest_path.exists():
    manifest_bytes = manifest_path.read_bytes()
    manifest = json.loads(manifest_bytes.decode("utf-8"))
    context_hashes["render_manifest.json"] = hashlib.sha256(manifest_bytes).hexdigest()
    for item in manifest.get("parts", []):
        filename = item.get("file", item.get("path", item["name"] + ".npz"))
        mesh(item["name"], G / filename, item.get("material", "shell"))

def area(name, location, energy, size, target=(0, 95, 35), color=(1, 1, 1)):
    d = bpy.data.lights.new(name, "AREA")
    d.energy, d.size, d.color = energy, size, color
    ob = bpy.data.objects.new(name, d)
    scene.collection.objects.link(ob)
    ob.location = location
    ob.rotation_euler = (Vector(target) - ob.location).to_track_quat("-Z", "Y").to_euler()

# Millimetre geometry needs larger lights and the corresponding light power.
area("large left softbox", (-240, -160, 320), 1800000, 260)
area("right fill softbox", (260, -20, 170), 1100000, 240)
area("rear edge softbox", (80, 340, 270), 2200000, 240)
area("lower front fill", (0, -260, -110), 550000, 200)

cd = bpy.data.cameras.new("review_camera")
cam = bpy.data.objects.new("review_camera", cd)
scene.collection.objects.link(cam)
scene.camera = cam
cd.type = "ORTHO"
cd.clip_start = .1
cd.clip_end = 3000
assembly = set(objects) - {"head"}
front_parts = assembly - {"rear", "battery", "straps"}

def render(name, direction, show, aspect=1.55, padding=1.14, target=None):
    for key, ob in objects.items():
        ob.hide_render = key not in show
    vs = np.concatenate([arrays[k] for k in show if k in arrays])
    if target is None:
        target = (vs.min(0) + vs.max(0)) / 2
    target = Vector(target)
    direction = Vector(direction).normalized()
    cam.location = target + 700 * direction
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    rot = cam.rotation_euler.to_matrix()
    right = np.array(rot @ Vector((1, 0, 0)))
    up = np.array(rot @ Vector((0, 1, 0)))
    xx, yy = vs @ right, vs @ up
    center = ((xx.max() + xx.min()) / 2, (yy.max() + yy.min()) / 2)
    # Frame the actual visible meshes, centering them in the image plane.
    off = (center[0] - np.dot(target, right)) * right + (center[1] - np.dot(target, up)) * up
    cam.location += Vector(off)
    cd.ortho_scale = max(np.ptp(xx), np.ptp(yy) * aspect) * padding
    scene.render.resolution_x = args.width
    scene.render.resolution_y = round(args.width / aspect)
    path = W / (name + ".png")
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    # Alpha compositing only: preserve every rendered pixel and silhouette.
    im = Image.open(path).convert("RGBA")
    bg = Image.new("RGBA", im.size, "white")
    bg.alpha_composite(im)
    bg.convert("RGB").save(path)
    rendered_views.append(name)
    return path

views = {
    "woad_front_angle": ((.55, -.86, -.32), assembly, 1.62, 1.10, None),
    "woad_inside_angle": ((-.61, .82, .53), assembly, 1.62, 1.10, None),
    "worn_side": ((-1, 0, .035), set(objects), 1.08, 1.10, None),
    "front": ((0, -1, 0), front_parts, 2.10, 1.13, None),
    "back": ((0, 1, 0), front_parts, 2.10, 1.13, None),
    "bottom": ((0, 0, -1), front_parts, 1.20, 1.13, None),
    "top": ((0, 0, 1), front_parts, 1.20, 1.13, None),
    "left": ((-1, 0, 0), front_parts, 1.85, 1.13, None),
    "right": ((1, 0, 0), front_parts, 1.85, 1.13, None),
    "service_open": ((-.45, .88, .54), front_parts - {"service_lid", "fasteners", "cable_gland"}, 1.55, 1.13, None),
    "front_low": ((.40, -1, -.30), front_parts, 1.7, 1.13, None),
}
for name, spec in views.items():
    if args.only is None or name in args.only:
        render(name, *spec)

def font(size):
    for path in (Path("C:/Windows/Fonts/segoeui.ttf"), Path("C:/Windows/Fonts/arial.ttf")):
        if path.exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default()

def fit(im, box):
    out = Image.new("RGB", box, "white")
    im = im.convert("RGB")
    factor = min(box[0] / im.width, box[1] / im.height)
    im = im.resize((round(im.width * factor), round(im.height * factor)), Image.Resampling.LANCZOS)
    out.paste(im, ((box[0] - im.width) // 2, (box[1] - im.height) // 2))
    return out

def comparison(name, crop, render_name, title):
    source = Image.open(R / "cover.png").convert("RGB")
    source = source.crop(crop)
    source.save(R / (name + "_source_crop.png"))
    new = Image.open(W / (render_name + ".png"))
    cell = (1100, 780)
    plate = Image.new("RGB", (2240, 876), "white")
    plate.paste(fit(source, cell), (10, 76))
    plate.paste(fit(new, cell), (1130, 76))
    draw = ImageDraw.Draw(plate)
    draw.text((34, 15), "WOAD | supplied cover.png", fill="#333b44", font=font(27))
    draw.text((1154, 15), title + " | actual delivered meshes", fill="#333b44", font=font(27))
    draw.line((1120, 76, 1120, 856), fill="#e2e6e9", width=2)
    plate.save(W / (name + ".png"))

if not args.no_comparison and (R / "cover.png").exists():
    for name, crop, render_name, title in [
        ("comparison_front", (334, 22, 895, 333), "woad_front_angle", "New front"),
        ("comparison_inside", (334, 334, 895, 672), "woad_inside_angle", "New front, inner view"),
        ("comparison_worn_side", (128, 79, 252, 222), "worn_side", "New front on repository headform"),
    ]:
        if (W / (render_name + ".png")).exists():
            comparison(name, crop, render_name, title)

if rendered_views:
    changed_inputs = [
        name for name, info in source_hashes.items()
        if hashlib.sha256((P.parent / info["path"]).read_bytes()).hexdigest() != info["sha256"]
    ]
    evidence = {
        "mesh_inputs": source_hashes,
        "context_inputs": context_hashes,
        "cover_sha256": hashlib.sha256((R / "cover.png").read_bytes()).hexdigest() if (R / "cover.png").exists() else None,
        "renderer_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "blender_version": bpy.app.version_string,
        "engine": args.engine, "samples": args.samples, "width_px": args.width,
        "rendered_views": rendered_views,
        "inputs_unchanged_on_completion": not changed_inputs,
        "changed_inputs": changed_inputs,
        "view_directions": {name: views[name][0] for name in rendered_views},
        "outputs": {
            name + ".png": hashlib.sha256((W / (name + ".png")).read_bytes()).hexdigest()
            for name in rendered_views
        },
    }
    (W / "render_source_hashes.json").write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    if changed_inputs:
        raise RuntimeError("Geometry changed during rendering; these outputs are stale: " + ", ".join(changed_inputs))

print("Render complete. All views show the delivered mesh geometry unchanged.", flush=True)
