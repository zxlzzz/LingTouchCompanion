"""Validate and slice the final structural 3MF with the saved H2C settings.

The actual delivered archive is the slicer input. No UI, printer, user preset,
or prior deliverable is changed. Temporary profiles and G-code are removed.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import json
import math
import re
import subprocess
import tempfile
import time
import xml.etree.ElementTree as ET
import zipfile

import numpy as np

P = Path(__file__).resolve().parent
BASE = P.parent
NS = "{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}"
SETTINGS_ENTRY = "Metadata/project_settings.config"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def jsonable(value):
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    raise TypeError(type(value).__name__)


def load_mesh(path):
    with np.load(path) as data:
        v, f = np.asarray(data["v"], float), np.asarray(data["f"], np.int64)
    # Existing exporters remove unreferenced vertices before writing the 3MF.
    used = np.unique(f)
    return v[used], np.searchsorted(used, f)


def inspect_archive(path, posed_path, body_path, angle):
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None, "Damaged ZIP member"
        model_files = [name for name in archive.namelist() if name.lower().endswith(".model")]
        assert model_files == ["3D/3dmodel.model"], model_files
        root = ET.fromstring(archive.read(model_files[0]))
        settings_raw = archive.read(SETTINGS_ENTRY)
        settings = json.loads(settings_raw.decode("utf-8-sig"))
    assert root.get("unit", "millimeter") == "millimeter"
    metadata = {node.get("name"): node.text for node in root.findall(NS + "metadata")}
    assert metadata.get("Application", "").startswith("BambuStudio-"), "Native Bambu project marker missing"
    assert metadata.get("BambuStudio:3mfVersion") == "1", "Native Bambu format version missing"
    objects = root.findall(NS + "resources/" + NS + "object")
    items = root.findall(NS + "build/" + NS + "item")
    assert len(objects) == len(items) == 1, "Final print must contain one physical body only"
    obj, item = objects[0], items[0]
    assert obj.get("type", "model") == "model"
    assert item.get("objectid") == obj.get("id")
    assert obj.find(NS + "components") is None, "Unexpected component indirection"
    identity = np.array([1, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0, 0], float)
    if item.get("transform"):
        assert np.array_equal(np.fromstring(item.get("transform"), sep=" "), identity)
    mesh = obj.find(NS + "mesh")
    assert mesh is not None
    v = np.array([[float(node.get(key)) for key in "xyz"]
                  for node in mesh.findall(NS + "vertices/" + NS + "vertex")])
    f = np.array([[int(node.get(key)) for key in ("v1", "v2", "v3")]
                  for node in mesh.findall(NS + "triangles/" + NS + "triangle")], dtype=np.int64)
    pv, pf = load_mesh(posed_path)
    bv, bf = load_mesh(body_path)
    assert np.array_equal(v, pv) and np.array_equal(f, pf), "3MF differs from final posed geometry"
    assert np.array_equal(f, bf), "Posed geometry changes the body topology"
    radians = math.radians(angle)
    rotation = np.array([[1, 0, 0], [0, math.cos(radians), -math.sin(radians)],
                         [0, math.sin(radians), math.cos(radians)]])
    rotated = bv @ rotation.T
    translations = v - rotated
    translation = translations[0]
    max_error = float(np.abs(translations - translation).max())
    assert max_error < 1e-9, "Archive is not the declared rigid pose of the revised body"
    assert abs(float(v[:, 2].min())) < 1e-8, "Body does not start on the bed"
    return settings, {
        "archive_mesh_vertices": len(v), "archive_mesh_triangles": len(f),
        "single_print_body": True, "pose_baked_in_vertices": True,
        "posed_geometry_readback_bit_exact": True,
        "body_to_print_rotation_x_deg": angle,
        "body_to_print_rotation_matrix": rotation.tolist(),
        "body_to_print_translation_mm": translation.tolist(),
        "max_rigid_pose_error_mm": max_error,
        "bounds_xyz_mm": [v.min(0).tolist(), v.max(0).tolist()],
        "settings_entry_sha256": hashlib.sha256(settings_raw).hexdigest(),
        "native_project_metadata": {key: metadata[key] for key in ("Application", "BambuStudio:3mfVersion")},
    }, v, f


def compact_metrics(candidate):
    statistics = [line for value in candidate.get("gcode", {}).values()
                  for line in value.get("statistics", [])]
    total_mass = None
    estimate_seconds = None
    for line in statistics:
        match = re.search(r"total filament weight \[g\]\s*:\s*([\d.]+)", line)
        if match:
            total_mass = float(match.group(1))
        match = re.search(r"total estimated time:\s*([^;]+)", line)
        if match:
            pieces = re.findall(r"(\d+)\s*([hms])", match.group(1))
            estimate_seconds = sum(int(n) * {"h": 3600, "m": 60, "s": 1}[unit] for n, unit in pieces)
    return {"support_mass_g": candidate.get("support_mass_g"), "total_filament_mass_g": total_mass,
            "estimated_print_seconds": estimate_seconds, "statistics": statistics,
            "first_layer_footprints": [value.get("first_layer", {}).get("raster_stroke_union")
                                       for value in candidate.get("gcode", {}).values()]}


def baseline(path, angle):
    evidence = json.loads(path.read_text("utf8"))
    candidates = [value for value in evidence["candidates"]
                  if abs(value["rotation_about_wearing_x_deg"] - angle) < 1e-6]
    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["pass"]
    return {"evidence_file": str(path), "evidence_sha256": sha(path),
            "angle_x_deg": angle, "settings_sha256": evidence["settings_sha256"],
            "source_hashes": evidence["source_hashes"], "metrics": compact_metrics(candidate)}


def support_spatial_evidence(raw, settings, geometry):
    """Compact path locations in print and wearing coordinates, not load analysis."""
    rotation = np.asarray(geometry["body_to_print_rotation_matrix"])
    translation = np.asarray(geometry["body_to_print_translation_mm"])
    filament_factor = math.pi * (float(settings["filament_diameter"][0]) / 2) ** 2 / 1000 * float(settings["filament_density"][0])
    xyz, last_e, absolute_e, absolute_xyz, role = np.zeros(3), 0., False, True, "Custom"
    token = re.compile(r"([XYZERIJ])([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)")
    rows = {}
    first_layer_support = []
    first_layer_model = []
    for line in raw.decode("utf8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith(("; FEATURE:", "; TYPE:")):
            role = line.split(":", 1)[1].strip()
        if line.startswith("M82"):
            absolute_e = True
        elif line.startswith("M83"):
            absolute_e = False
        elif line == "G90":
            absolute_xyz = True
        elif line == "G91":
            absolute_xyz = False
        elif line.startswith("G92 "):
            values = {k: float(v) for k, v in token.findall(line.split(";", 1)[0])}
            if "E" in values:
                last_e = values["E"]
        elif line.startswith(("G0 ", "G1 ", "G2 ", "G3 ")):
            values = {k: float(v) for k, v in token.findall(line.split(";", 1)[0])}
            old = xyz.copy()
            for i, key in enumerate("XYZ"):
                if key in values:
                    xyz[i] = values[key] if absolute_xyz else xyz[i] + values[key]
            amount = values.get("E", last_e if absolute_e else 0.)
            if absolute_e:
                amount -= last_e
                if "E" in values:
                    last_e = values["E"]
            if amount <= 0 or role == "Custom" or not any(k in values for k in "XY"):
                continue
            points = np.array([old, xyz])
            wearing = (points - translation) @ rotation
            is_support = role in ("Support", "Support interface")
            if abs(xyz[2] - float(settings["initial_layer_print_height"])) < 1e-5:
                if is_support:
                    first_layer_support.append(points[:, :2])
                elif role not in ("Brim", "Skirt", "Wipe tower"):
                    first_layer_model.append(points[:, :2])
            if not is_support:
                continue
            midpoint = wearing.mean(0)
            side = "left_of_x_minus65" if midpoint[0] < -65 else "right_of_x65" if midpoint[0] > 65 else "central_x_plusminus65"
            ykey = "y_below0" if midpoint[1] < 0 else "y_0to25" if midpoint[1] < 25 else "y_25to45" if midpoint[1] < 45 else "y_45to130" if midpoint[1] < 130 else "y_130plus"
            height = "zprint_0to10" if xyz[2] < 10 else "zprint_10to50" if xyz[2] < 50 else "zprint_50to100" if xyz[2] < 100 else "zprint_100plus"
            key = (role, side, ykey, height)
            row = rows.setdefault(key, {"role": role, "wearing_x_region": side, "wearing_y_region": ykey,
                                       "print_height_region": height, "extrusion_mm": 0., "segments": 0,
                                       "print_min_xyz_mm": np.full(3, np.inf), "print_max_xyz_mm": np.full(3, -np.inf),
                                       "wearing_min_xyz_mm": np.full(3, np.inf), "wearing_max_xyz_mm": np.full(3, -np.inf)})
            row["extrusion_mm"] += amount
            row["segments"] += 1
            for name, points in (("print", points), ("wearing", wearing)):
                row[name + "_min_xyz_mm"] = np.minimum(row[name + "_min_xyz_mm"], points.min(0))
                row[name + "_max_xyz_mm"] = np.maximum(row[name + "_max_xyz_mm"], points.max(0))
    result = []
    for row in rows.values():
        row["mass_g"] = round(row["extrusion_mm"] * filament_factor, 4)
        row["extrusion_mm"] = round(row["extrusion_mm"], 3)
        result.append(row)
    proximity = {}
    if first_layer_model and first_layer_support:
        from scipy.spatial import cKDTree
        support_points = np.concatenate(first_layer_support)
        model_points = np.concatenate(first_layer_model)
        distances = cKDTree(support_points).query(model_points)[0]
        proximity = {"minimum_extruding_endpoint_distance_mm": float(distances.min()),
                     "median_nearest_extruding_endpoint_distance_mm": float(np.median(distances)),
                     "model_endpoint_count": len(model_points), "support_endpoint_count": len(support_points),
                     "note": "Endpoint proximity only, without line widths or arc interiors; not a connectivity proof."}
    return {"groups": sorted(result, key=lambda x: -x["mass_g"]), "first_layer_support_proximity": proximity,
            "method": "Positive support extrusion grouped by segment midpoint after inverse pose. Endpoint bounds omit possible arc extrema; support location does not identify the supported feature by itself."}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--archive", type=Path, default=P / "Front_Simple_Print.3mf")
    ap.add_argument("--posed-mesh", type=Path, default=P / "geometry/front_print.npz")
    ap.add_argument("--body", type=Path, default=P / "geometry/front_body.npz")
    ap.add_argument("--saved-settings", type=Path, default=BASE / "camera_mount/project_settings.json")
    ap.add_argument("--angle", type=float, default=135.0)
    ap.add_argument("--engine", type=Path, default=Path("D:/Bambu Studio/bambu-studio.exe"))
    ap.add_argument("--timeout", type=int, default=600)
    ap.add_argument("--report", type=Path, default=P / "checks/slice.json")
    args = ap.parse_args()
    args.report.parent.mkdir(parents=True, exist_ok=True)
    source_paths = [args.archive, args.posed_mesh, args.body, args.saved_settings]
    source_hashes = {str(path.resolve()): sha(path) for path in source_paths}
    report = {"purpose": "Actual final 3MF, preserved H2C 0.2 mm settings, structural revision verification",
              "source_hashes": source_hashes, "pass": False,
              "engine": str(args.engine), "engine_sha256": sha(args.engine),
              "verifier_sha256": sha(Path(__file__)),
              "limitations": "Generated paths, support estimates, and footprint calculations do not prove physical adhesion, strength, comfort, or support removal."}

    def save():
        args.report.write_text(json.dumps(report, indent=2, default=jsonable), encoding="utf8")

    started = time.monotonic()
    save()
    try:
        helpers = module("structural_preserved_helpers", BASE / "print_check.py")
        actual = module("structural_actual_settings", BASE / "onepiece/evaluate.py")
        settings, geometry, v, f = inspect_archive(args.archive, args.posed_mesh, args.body, args.angle)
        report["geometry"] = geometry
        report["exact_lowest_plane_model_contact"] = helpers.bed_contact(v, f)
        saved_raw = args.saved_settings.read_bytes()
        saved = json.loads(saved_raw.decode("utf-8-sig"))
        report["source_saved_settings_sha256"] = hashlib.sha256(saved_raw).hexdigest()
        delta = {key: {"saved": saved.get(key), "final": settings.get(key)}
                 for key in sorted(set(saved) | set(settings))
                 if key not in saved or key not in settings or saved[key] != settings[key]}
        assert set(delta) <= {"brim_type", "brim_width"}, "Unexpected saved print setting changes: " + repr(delta)
        if delta:
            assert settings["brim_type"] == "outer_only" and float(settings["brim_width"]) == 5
        report["saved_settings_delta"] = delta
        report["all_other_saved_settings_equal"] = True
        profiles, names, provenance, assignments, omitted = actual.actual_profiles(helpers, args.engine.parent, settings)
        machine, process, filament = (profiles[kind] for kind in ("machine", "process", "filament"))
        assert names["machine"] == "Bambu Lab H2C 0.2 nozzle"
        assert float(settings["layer_height"]) == .1 and int(settings["wall_loops"]) == 4
        bed = np.array([[float(n) for n in point.split("x")] for point in machine["printable_area"]])
        assert np.all(v[:, :2].min(0) >= bed.min(0)) and np.all(v[:, :2].max(0) <= bed.max(0))
        report.update(selected_profiles=names, profile_sources=provenance,
                      saved_setting_profile_assignments=assignments, saved_keys_not_native_preset_fields=omitted)
        summary_keys = ["printer_settings_id", "print_settings_id", "filament_settings_id", "curr_bed_type",
                        "nozzle_diameter", "layer_height", "initial_layer_print_height", "wall_loops",
                        "line_width", "initial_layer_line_width", "filament_max_volumetric_speed",
                        "sparse_infill_density", "sparse_infill_pattern", "enable_support", "support_type",
                        "support_threshold_angle", "support_top_z_distance", "support_bottom_z_distance",
                        "support_on_build_plate_only", "brim_type", "brim_width", "brim_object_gap",
                        "support_object_first_layer_gap", "support_object_xy_distance", "tree_support_auto_brim",
                        "tree_support_brim_width", "raft_layers"]
        report["final_saved_settings_summary"] = {key: settings.get(key) for key in summary_keys}
        report["baselines"] = {}
        save()
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = subprocess.SW_HIDE
        with tempfile.TemporaryDirectory(prefix="final_structural_slice_") as temporary:
            scratch = Path(temporary)
            report["native_embedded_settings_only"] = True
            report["external_preset_overrides"] = False
            report["profile_resolution_usage"] = "Read-only reference validation and parser material density; no profile files supplied to slicer."
            command = [str(args.engine), "--arrange", "0", "--orient", "0", "--ensure-on-bed", "--slice", "0", "--debug", "2",
                       "--mstpp", str(args.timeout), "--outputdir", str(scratch), str(args.archive.resolve())]
            report["slicer_input"] = str(args.archive.resolve())
            report["slicer_input_is_actual_deliverable"] = True
            save()
            print("Slicing final structural 3MF with preserved saved settings.", flush=True)
            result = subprocess.run(command, cwd=scratch, capture_output=True, timeout=args.timeout + 60,
                                    startupinfo=startup, creationflags=subprocess.CREATE_NO_WINDOW)
            engine_path = scratch / "result.json"
            report["engine_report"] = json.loads(engine_path.read_text("utf8")) if engine_path.exists() else {}
            report["exit_code"] = result.returncode
            report["diagnostics"] = [line for line in (result.stdout + result.stderr).decode("utf8", errors="replace").splitlines()
                                     if any(term in line.lower() for term in ("warning", "error", "failed"))][-30:]
            gcode = {}
            for path in scratch.rglob("*.gcode"):
                raw = path.read_bytes()
                item = helpers.parse_gcode(raw, float(filament["filament_diameter"][0]), float(filament["filament_density"][0]))
                config_comments = dict(re.findall(r"^;\s*([a-z][a-z0-9_]*)\s*=\s*(.*?)\s*$", raw.decode("utf8", errors="replace"), re.MULTILINE))
                item["effective_config_comments"] = {key: config_comments[key] for key in summary_keys if key in config_comments}
                assert "nozzle_diameter" in config_comments, "Missing native effective nozzle diameter"
                assert all(abs(float(value) - .2) < 1e-6 for value in re.findall(r"[\d.]+", config_comments["nozzle_diameter"])), "Sliced nozzle differs from saved settings"
                for key in ("layer_height", "initial_layer_print_height", "wall_loops", "line_width", "initial_layer_line_width",
                            "support_threshold_angle", "support_top_z_distance", "support_bottom_z_distance", "brim_width", "brim_object_gap"):
                    assert key in config_comments, "Missing native effective setting: " + key
                    assert abs(float(config_comments[key]) - float(settings[key])) < 1e-6, "Native effective setting mismatch: " + key
                for key in ("curr_bed_type", "sparse_infill_density", "sparse_infill_pattern", "enable_support", "support_type",
                            "support_on_build_plate_only", "brim_type"):
                    assert config_comments.get(key) == settings[key], "Native effective setting mismatch: " + key
                assert float(config_comments["filament_max_volumetric_speed"]) == float(settings["filament_max_volumetric_speed"][0])
                item["first_layer"] = actual.first_layer_evidence(raw, settings)
                item["support_height_bins"] = actual.support_height_bins(raw, settings)
                item["support_spatial_evidence"] = support_spatial_evidence(raw, settings, geometry)
                gcode[path.name] = item
            report["gcode"] = gcode
            report["adhesion_evidence"] = {
                "flat_model_mesh_contact_mm2": report["exact_lowest_plane_model_contact"]["total_area_mm2"],
                "first_layer_model_extrusion_footprint_mm2": sum(item["first_layer"]["raster_stroke_union"]["model"]["area_mm2"] for item in gcode.values()),
                "first_layer_brim_extrusion_footprint_mm2": sum(item["first_layer"]["raster_stroke_union"]["brim"]["area_mm2"] for item in gcode.values()),
                "brim_extrusion_generated": any("Brim" in item["feature_sections"] for item in gcode.values()),
                "note": "Flat mesh contact and generated first-layer strokes are separate evidence. Support foundation area is not counted as direct model adhesion. No physical print test was performed.",
            }
            report["support_mass_g"] = round(sum(feature["mass_g"] for item in gcode.values()
                                                  for role, feature in item["extruded_paths_by_feature"].items()
                                                  if role in ("Support", "Support interface")), 3)
            report["final_metrics"] = compact_metrics(report)
            report["comparison_deltas"] = {}
            for name, data in report["baselines"].items():
                before = data["metrics"]
                report["comparison_deltas"][name] = {key: round(report["final_metrics"][key] - before[key], 3)
                                                      for key in ("support_mass_g", "total_filament_mass_g", "estimated_print_seconds")
                                                      if report["final_metrics"][key] is not None and before[key] is not None}
            report["pass"] = bool(result.returncode == 0 and report["engine_report"].get("return_code") == 0
                                  and len(gcode) == 1)
            if report["pass"]:
                assert abs(report["engine_report"]["layer_height"] - .1) < 1e-6
                assert report["engine_report"]["wall_loops"] == 4
        report["temporary_files_removed"] = True
    except Exception as error:
        report["pass"] = False
        report["failure"] = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        report["source_files_unchanged"] = all(sha(path) == value for path, value in source_hashes.items())
        report["pass"] = report["pass"] and report["source_files_unchanged"]
        report["elapsed_seconds"] = round(time.monotonic() - started, 3)
        save()
    print(json.dumps({key: report[key] for key in ("pass", "saved_settings_delta", "final_metrics", "comparison_deltas", "diagnostics")}, indent=2), flush=True)
    assert report["pass"], "Final delivered archive slicing failed"


if __name__ == "__main__":
    main()
