"""Rebuild the approved rear pocket and write one millimetre-unit 3MF.

Keep rear_inputs beside this script. Those NPZ files contain the approved
head-derived curved tray and curved joining boundary, not the final part.
This script clips the tray/ribs, builds the pocket, bump, notch, ears and
slots, and unions them. It never reads a cached final unified mesh.
Dependencies: numpy==1.26.4, manifold3d==3.5.4; Python 3.11 recommended.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import zipfile

import manifold3d as md
import numpy as np

HERE = Path(__file__).resolve().parent
INPUTS = HERE / "rear_inputs"
M = md.Manifold


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def checked(m: md.Manifold, label: str) -> md.Manifold:
    if m.status() != md.Error.NoError or m.is_empty():
        raise RuntimeError(f"{label}: invalid or empty solid ({m.status()})")
    return m


def load_reference(name: str, manifest: dict) -> md.Manifold:
    path = INPUTS / name
    expected = manifest[name]["sha256"]
    actual = sha256(path)
    if actual != expected:
        raise ValueError(f"Input geometry changed: {name}; expected {expected}, got {actual}")
    with np.load(path, allow_pickle=False) as a:
        mesh = md.Mesh64(
            vert_properties=np.ascontiguousarray(a["v"], dtype=np.float64),
            tri_verts=np.ascontiguousarray(a["f"], dtype=np.uint64),
        )
    return checked(M(mesh), name)


def box(lo, hi) -> md.Manifold:
    lo = np.asarray(lo, dtype=np.float64)
    hi = np.asarray(hi, dtype=np.float64)
    return M.cube(tuple(hi - lo)).translate(tuple(lo))


def mesh_arrays(m: md.Manifold):
    mesh = m.to_mesh64()
    return np.asarray(mesh.vert_properties)[:, :3], np.asarray(mesh.tri_verts)


def describe(m: md.Manifold) -> dict:
    v, f = mesh_arrays(m)
    return {
        "vertices": len(v),
        "triangles": len(f),
        "bounds_xyz_mm": [v.min(axis=0).tolist(), v.max(axis=0).tolist()],
        "solid_volume_mm3": float(m.volume()),
        "connected_components": len(m.decompose()),
        "mesh_status": str(m.status()),
    }


def build_rear() -> tuple[md.Manifold, dict, dict]:
    manifest = json.loads((INPUTS / "input_manifest.json").read_text(encoding="utf-8"))
    curved_tray = load_reference("head_derived_tray_reference.npz", manifest)
    joining_boundary = load_reference("curved_join_boundary_reference.npz", manifest)

    # Exact approved surface geometry, narrowed to 80 mm without re-fitting.
    tray = checked(curved_tray ^ box([-40, 110, 8.1], [40, 204, 55.3]), "tray")
    left_rib = checked(joining_boundary ^ box([-40, 110, 8.1], [-37, 203.4, 55.3]), "left rib")
    right_rib = checked(joining_boundary ^ box([37, 110, 8.1], [40, 203.4, 55.3]), "right rib")
    central_join = checked(joining_boundary ^ box([-4, 202, 51.2], [4, 203.4, 55.3]), "central join")

    # These operations and sphere tessellation match the approved pocket.
    py, z0, ztop = 203.3, 8.2, 55.2
    pocket = box([-60.8, py, z0], [60.8, py + 19.6, ztop])
    pocket -= box([-58.8, py + 2, z0 + 2], [58.8, py + 17.6, ztop + .1])
    pocket -= box([58.7, py + 4.3, ztop - 35], [60.9, py + 15.3, ztop + .1])
    pocket += M.sphere(1, 48).scale((1, .8, .8)).translate((0, py + 2, ztop - 1.5))
    pocket = checked(pocket, "pocket")

    components = {
        "rear_tray": tray,
        "rear_left_rib": left_rib,
        "rear_right_rib": right_rib,
        "rear_central_join": central_join,
        "rear_box": pocket,
    }
    for side, name in [(-1, "left"), (1, "right")]:
        if side > 0:
            ear = box([65.3, 200.3, 23.2], [68.3, 211.3, 55.2])
            root = box([60.7, 207, 23.2], [66.3, 211.3, 55.2])
            slot = box([64.3, 203.3, 26.2], [69.3, 206.3, 52.2])
        else:
            ear = box([-68.3, 200.3, 23.2], [-65.3, 211.3, 55.2])
            root = box([-66.3, 207, 23.2], [-60.7, 211.3, 55.2])
            slot = box([-69.3, 203.3, 26.2], [-64.3, 206.3, 52.2])
        components[f"rear_{name}_ear"] = checked(ear - slot, f"{name} ear")
        components[f"rear_{name}_ear_root"] = root

    rear = checked(M.batch_boolean(list(components.values()), md.OpType.Add), "unified rear")
    if len(rear.decompose()) != 1:
        raise RuntimeError("Final rear must be one connected closed solid")
    values = {
        "units": "millimeter",
        "design": "Exact approved rear geometry; bottom-down print placement only.",
        "curve_inputs": {name: {"sha256": data["sha256"]} for name, data in manifest.items() if isinstance(data, dict)},
        "components": {name: describe(m) for name, m in components.items()},
        "unified": describe(rear),
        "tray_width_mm": 80.,
        "tray_x_mm": [-40., 40.],
        "tray_z_mm": [8.2, 55.2],
        "rib_x_thickness_mm": 3.,
        "rib_left_x_mm": [-40., -37.],
        "rib_right_x_mm": [37., 40.],
        "central_join_xz_mm": [[-4., 51.2], [4., 55.2]],
        "minimum_original_center_gap_y_mm": 203.3 - 203.24443660487455,
        "box_outer_width_ydepth_height_mm": [121.6, 19.6, 47.],
        "box_inner_width_ydepth_height_mm": [117.6, 15.6, 45.],
        "box_wall_and_bottom_mm": 2.,
        "battery_nominal_width_height_thickness_mm": [117., 47., 15.],
        "battery_side_clearance_mm": .3,
        "battery_front_back_clearance_mm": .3,
        "battery_top_exposure_mm": 2.,
        "bump_inward_mm": .8,
        "bump_shape": "Sphere radius1, 48 segments, scaled XYZ(1,.8,.8)",
        "bump_center_xyz_mm": [0., 205.3, 53.7],
        "bump_throat_y_mm": 14.8,
        "nominal_battery_required_elastic_relief_mm": .2,
        "bump_physical_insertion_removal": "Not checked",
        "port_notch_width_y_depth_z_mm": [11., 35.],
        "port_notch_y_mm": [207.6, 218.6],
        "port_notch_z_mm": [20.2, 55.2],
        "ear_height_xthickness_mm": [32., 3.],
        "ear_z_mm": [23.2, 55.2],
        "slot_height_z_width_y_mm": [26., 3.],
        "slot_cut_axis": "X",
        "slot_y_mm": [203.3, 206.3],
        "slot_z_mm": [26.2, 52.2],
        "ear_root_y_mm": [207., 211.3],
        "ear_underside_height_above_platform_mm": 15.,
        "ear_outer_side_projection_beyond_box_mm": 7.5,
        "band_nominal_width_mm": 25.,
        "band_outer_front_edge_contacts_xyz_mm": {"left": [-68.3, 203.3, 39.2], "right": [68.3, 203.3, 39.2]},
        "old_bulk_fill_excluded": True,
        "print_orientation": "World bottomZ8.2 faces down; translation only, no rotation.",
        "print_support": "Support the underside of both side ears/root bridges (15mm above bed,7.5mm lateral projection) and any local curved-tray overhang identified by the slicer. Keep support out of the pocket and slots where possible.",
        "slicer_and_physical_strength": "Not checked",
        "whole_headset_wearability": "Not established by this rear-part export",
    }
    return rear, components, values


def write_3mf(path: Path, rear: md.Manifold) -> dict:
    v, f = mesh_arrays(rear)
    shift = -v.min(axis=0)
    placed = v + shift
    xml = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<model unit="millimeter" xml:lang="en-US" xmlns="http://schemas.microsoft.com/3dmanufacturing/core/2015/02">',
        '<metadata name="Title">Final rear pocket - bottom down</metadata>',
        '<resources><object id="1" type="model" name="Rear"><mesh><vertices>',
    ]
    xml.extend('<vertex x="%.17g" y="%.17g" z="%.17g"/>' % tuple(row) for row in placed)
    xml.append('</vertices><triangles>')
    xml.extend('<triangle v1="%d" v2="%d" v3="%d"/>' % tuple(row) for row in f)
    xml.append('</triangles></mesh></object></resources><build><item objectid="1"/></build></model>')
    ct = '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="model" ContentType="application/vnd.ms-package.3dmanufacturing-3dmodel+xml"/></Types>'
    rel = '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rel0" Target="/3D/3dmodel.model" Type="http://schemas.microsoft.com/3dmanufacturing/2013/01/3dmodel"/></Relationships>'
    path.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", ct)
        archive.writestr("_rels/.rels", rel)
        archive.writestr("3D/3dmodel.model", "".join(xml))
    return {
        "translation_xyz_mm": shift.tolist(),
        "rotation_matrix_xyz": np.eye(3, dtype=int).tolist(),
        "print_bounds_xyz_mm": [placed.min(axis=0).tolist(), placed.max(axis=0).tolist()],
        "dimensions_xyz_mm": np.ptp(placed, axis=0).tolist(),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "Rear_Final.3mf")
    parser.add_argument("--audit-dir", type=Path, help="Optional QA mesh output; not needed to regenerate the 3MF.")
    args = parser.parse_args()
    rear, components, values = build_rear()
    values["print_placement"] = write_3mf(args.output, rear)
    values["final_3mf_sha256"] = sha256(args.output)
    values["generator_sha256"] = sha256(Path(__file__))
    if args.audit_dir:
        args.audit_dir.mkdir(parents=True, exist_ok=True)
        for name, m in {**components, "rear_unified": rear}.items():
            v, f = mesh_arrays(m)
            np.savez_compressed(args.audit_dir / (name + ".npz"), v=v, f=f)
    (args.output.parent / "rear_geometry_values.json").write_text(json.dumps(values, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(args.output.resolve()), "unified": values["unified"], "placement": values["print_placement"]}, indent=2))


if __name__ == "__main__":
    main()
