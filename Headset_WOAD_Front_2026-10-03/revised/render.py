"""Render only the separately saved revision; leave previous outputs untouched.

Reuse the existing renderer's lights, materials, camera angles and comparison
scale. Final files are three WOAD comparisons, one inspection plate and their
source manifest. The inspection plate shows the underside nose support and the
straight temples from above. No replacement geometry or modifiers are used.
"""
from pathlib import Path
import hashlib
import json

HERE = Path(__file__).resolve().parent
BASE = HERE.parent
TEMPLATE = BASE / "render.py"
WRAPPER = Path(__file__).resolve()
wrapper_hash = hashlib.sha256(WRAPPER.read_bytes()).hexdigest()
template_bytes = TEMPLATE.read_bytes()
template_hash = hashlib.sha256(template_bytes).hexdigest()
source = template_bytes.decode("utf-8")


def replace_once(old, new):
    global source
    if source.count(old) != 1:
        raise RuntimeError("Renderer template changed; inspect this wrapper: " + old[:100])
    source = source.replace(old, new, 1)


replace_once('G = P / "geometry"', 'G = P / "revised" / "geometry"')
replace_once('W = P / "views"', 'W = P / "revised" / "views"')
replace_once('REAR = P.parent / "Headset_Rear" / "geometry"',
             'REAR = P.parent / "Headset_Rear" / "revised" / "geometry"')

# Only the two new bodies are mandatory revision geometry. Unchanged camera,
# straps and battery references are read from the preserved previous sources.
replace_once('mesh("front", G / "front_body.npz", "shell")', '''
def reference_path(directory, filename, fallback):
    candidate = directory / filename
    return candidate if candidate.exists() else fallback / filename

mesh("front", G / "front_body.npz", "shell")''')
for name, filename, material in (
    ("camera", "camera.npz", "camera"),
    ("retention_band", "retention_band.npz", "band"),
    ("straps", "connection_straps.npz", "strap"),
):
    replace_once(f'mesh("{name}", G / "{filename}", "{material}")',
                 f'mesh("{name}", reference_path(G, "{filename}", P / "geometry"), "{material}")')
replace_once('mesh("camera_optics", G / "camera_optics.npz", "lens", optional=True)',
             'mesh("camera_optics", reference_path(G, "camera_optics.npz", P / "geometry"), "lens", optional=True)')
replace_once('mesh("battery", REAR / "battery.npz", "battery")',
             'mesh("battery", reference_path(REAR, "battery.npz", P.parent / "Headset_Rear" / "geometry"), "battery")')

replace_once('final_views = ("woad_front_angle", "woad_inside_angle", "worn_side")', '''
views["nose_support"] = ((.35, .90, -.55), {"front"}, 1.40, 1.14, None)
views["straight_legs"] = ((0, 0, 1), {"front"}, 1.20, 1.10, None)
final_views = ("woad_front_angle", "woad_inside_angle", "worn_side", "nose_support", "straight_legs")''')
replace_once('''for name, spec in views.items():
    if name in requested_views:
        render(name, *spec)''', '''for name, spec in views.items():
    if name in requested_views:
        if name == "nose_support":
            full_vertices = arrays["front"]
            selection = ((np.abs(full_vertices[:, 0]) < 44) &
                         (full_vertices[:, 1] < 45) & (full_vertices[:, 2] < 44))
            if np.count_nonzero(selection) < 100:
                raise RuntimeError("Nose inspection framing contains too little delivered geometry.")
            arrays["front"] = full_vertices[selection]
            try:
                render(name, *spec)
            finally:
                arrays["front"] = full_vertices
        else:
            render(name, *spec)''')

namespace = {"__name__": "__main__", "__file__": str(TEMPLATE)}
exec(compile(source, str(TEMPLATE), "exec"), namespace)

W = namespace["W"]
if W != (HERE / "views").resolve():
    raise RuntimeError("Revision renders must remain in revised/views.")

Image = namespace["Image"]
ImageDraw = namespace["ImageDraw"]
font = namespace["font"]
fit = namespace["fit"]
manifest_path = W / "render_source_hashes.json"
manifest = json.loads(manifest_path.read_text("utf-8"))
rendered = manifest["rendered_views"]

if {"nose_support", "straight_legs"}.issubset(rendered):
    cell = (1000, 1000)
    plate = Image.new("RGB", (2040, 1100), "white")
    for position, name in ((10, "nose_support"), (1030, "straight_legs")):
        plate.paste(fit(Image.open(W / (name + ".png")), cell), (position, 80))
    draw = ImageDraw.Draw(plate)
    draw.text((30, 20), "Integral nose support | underside", fill="#333b44", font=font(27))
    draw.text((1050, 20), "Straight temples | top", fill="#333b44", font=font(27))
    draw.line((1020, 80, 1020, 1080), fill="#e2e6e9", width=2)
    plate.save(W / "inspection_details.png")

if hashlib.sha256(TEMPLATE.read_bytes()).hexdigest() != template_hash:
    raise RuntimeError("Renderer template changed during rendering.")
if hashlib.sha256(WRAPPER.read_bytes()).hexdigest() != wrapper_hash:
    raise RuntimeError("Revision renderer changed during rendering.")
manifest["renderer_wrapper"] = {"path": str(WRAPPER.relative_to(BASE.parent)).replace("\\", "/"),
                                "sha256": wrapper_hash}
manifest["renderer_template"] = {"path": str(TEMPLATE.relative_to(BASE.parent)).replace("\\", "/"),
                                 "sha256": template_hash}
manifest["inspection_framing"] = {
    "nose_support": "Viewport frames delivered front vertices abs(X)<44, Y<45, Z<44 mm; mesh unchanged.",
    "straight_legs": "Full delivered front, orthographic top view."
}
outputs = list(manifest["comparison_plates"])
if {"nose_support", "straight_legs"}.issubset(rendered):
    outputs.append("inspection_details")
manifest["outputs"] = {name + ".png": hashlib.sha256((W / (name + ".png")).read_bytes()).hexdigest()
                       for name in outputs}

# These raw views are temporary ingredients of the saved comparison/detail
# plates. Delete only this revision renderer's exact known raw filenames.
for name in rendered:
    (W / (name + ".png")).unlink(missing_ok=True)
manifest["temporary_raw_views_removed"] = True
manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
print("Revision comparisons and inspection plate saved; prior files untouched.", flush=True)
