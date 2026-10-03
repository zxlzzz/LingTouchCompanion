"""Slice the one-piece front with the installed Bambu engine; retain evidence only.

The final wearing-coordinate 3MF is never rewritten. A temporary single-body
STL is rotated/placed for slicing; camera, head and retention-band references
are excluded. Temporary STL and G-code files are removed afterward.
"""
from pathlib import Path
import argparse
import hashlib
import io
import json
import math
import re
import struct
import subprocess
import sys
import tempfile
import time

import numpy as np

P = Path(__file__).resolve().parent
DEFAULT_MACHINE = "Bambu Lab H2C 0.2 nozzle"
DEFAULT_PROCESS = "0.10mm Standard @BBL H2C 0.2 nozzle"
DEFAULT_FILAMENT = "Bambu PLA Basic @BBL H2C 0.2 nozzle"


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def full_profile(root, kind, name, chain=None):
    chain = [] if chain is None else chain
    path = root / "resources" / "profiles" / "BBL" / kind / (name + ".json")
    if name in [item["name"] for item in chain]:
        raise ValueError("Cyclic profile inheritance: " + name)
    raw = path.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    chain.append({"name": name, "path": str(path), "sha256": hashlib.sha256(raw).hexdigest()})
    parent = data.get("inherits")
    merged, chain = full_profile(root, kind, parent, chain) if parent else ({}, chain)
    merged.update(data)
    merged.pop("inherits", None)
    merged.update({"name": name, "type": kind, "from": "system", "instantiation": "true"})
    return merged, chain


def binary_stl(path, v, f):
    triangles = v[f]
    normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    lengths = np.linalg.norm(normals, axis=1)
    normals /= np.maximum(lengths[:, None], 1e-30)
    dtype = np.dtype([("normal", "<f4", (3,)), ("triangle", "<f4", (3, 3)), ("attribute", "<u2")])
    records = np.zeros(len(f), dtype=dtype)
    records["normal"] = normals
    records["triangle"] = triangles
    with path.open("wb") as stream:
        stream.write(b"Temporary one-piece headset front slice check".ljust(80, b" "))
        stream.write(struct.pack("<I", len(f)))
        stream.write(records.tobytes())


def parse_gcode(raw, filament_diameter, filament_density):
    text = raw.decode("utf-8", errors="replace")
    comments = [line.strip() for line in text.splitlines() if line.startswith(";")]
    statistics = [line for line in comments if any(term in line.lower() for term in (
        "total estimated time", "estimated printing time", "filament used", "total layer number",
        "filament cost", "model printing time", "total filament", "support filament"))]
    roles = {}
    for match in re.finditer(r"^;\s*(?:FEATURE|TYPE):\s*(.+)$", text, re.MULTILINE):
        role = match.group(1).strip()
        roles[role] = roles.get(role, 0) + 1
    layers = {match.group(1) for match in re.finditer(r"^;\s*layer num/total_layer_count:\s*(\d+)", text, re.MULTILINE)}
    # Inspect generated extrusion paths, not merely the existence of support
    # settings. Track relative/absolute E independently from XYZ positioning.
    xyz = [0.0, 0.0, 0.0]
    last_e, absolute_e, absolute_xyz, role = 0.0, False, True, "Custom"
    paths = {}
    token = re.compile(r"([XYZERIJ])([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)")
    for line in text.splitlines():
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
            values = dict((key, float(value)) for key, value in token.findall(line.split(";", 1)[0]))
            if "E" in values:
                last_e = values["E"]
        elif line.startswith(("G0 ", "G1 ", "G2 ", "G3 ")):
            values = dict((key, float(value)) for key, value in token.findall(line.split(";", 1)[0]))
            old_xyz = xyz[:]
            for i, key in enumerate("XYZ"):
                if key in values:
                    xyz[i] = values[key] if absolute_xyz else xyz[i] + values[key]
            amount = values.get("E", last_e if absolute_e else 0.0)
            if absolute_e:
                amount -= last_e
                if "E" in values:
                    last_e = values["E"]
            if amount <= 0 or role == "Custom" or not any(key in values for key in "XY"):
                continue
            info = paths.setdefault(role, {"extrusion_mm": 0.0, "segments": 0,
                    "min_xyz_mm": [float("inf")] * 3, "max_xyz_mm": [-float("inf")] * 3})
            info["extrusion_mm"] += amount
            info["segments"] += 1
            for i in range(3):
                info["min_xyz_mm"][i] = min(info["min_xyz_mm"][i], old_xyz[i], xyz[i])
                info["max_xyz_mm"][i] = max(info["max_xyz_mm"][i], old_xyz[i], xyz[i])
            if line.startswith(("G2 ", "G3 ")) and ("I" in values or "J" in values):
                centre = [old_xyz[0] + values.get("I", 0), old_xyz[1] + values.get("J", 0)]
                radius = math.hypot(values.get("I", 0), values.get("J", 0))
                start_angle = math.atan2(old_xyz[1] - centre[1], old_xyz[0] - centre[0])
                end_angle = math.atan2(xyz[1] - centre[1], xyz[0] - centre[0])
                clockwise = line.startswith("G2 ")
                sweep = ((start_angle - end_angle) if clockwise else (end_angle - start_angle)) % (2 * math.pi)
                full_circle = math.hypot(xyz[0] - old_xyz[0], xyz[1] - old_xyz[1]) < 1e-6
                for angle in (0, math.pi / 2, math.pi, 3 * math.pi / 2):
                    distance = ((start_angle - angle) if clockwise else (angle - start_angle)) % (2 * math.pi)
                    if full_circle or distance <= sweep + 1e-7:
                        point = [centre[0] + radius * math.cos(angle), centre[1] + radius * math.sin(angle)]
                        for i in range(2):
                            info["min_xyz_mm"][i] = min(info["min_xyz_mm"][i], point[i])
                            info["max_xyz_mm"][i] = max(info["max_xyz_mm"][i], point[i])
    for info in paths.values():
        info["extrusion_mm"] = round(info["extrusion_mm"], 3)
        info["volume_cm3"] = round(info["extrusion_mm"] * math.pi * (filament_diameter / 2) ** 2 / 1000, 4)
        info["mass_g"] = round(info["volume_cm3"] * filament_density, 3)
    return {"statistics": statistics, "feature_sections": roles, "layer_markers": len(layers),
            "generator_comments": [line for line in comments if "generated by" in line.lower()][:2],
            "extruded_paths_by_feature": paths,
            "arc_bounds_method": "G2_G3_IJ_sector_cardinal_extrema_and_endpoints",
            "gcode_bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--bambu-root", type=Path, default=Path("D:/Bambu Studio"))
    parser.add_argument("--machine", default=DEFAULT_MACHINE)
    parser.add_argument("--process", default=DEFAULT_PROCESS)
    parser.add_argument("--filament", default=DEFAULT_FILAMENT)
    parser.add_argument("--tilt-x", type=float, default=0.0)
    parser.add_argument("--support-angle", type=float, default=35.0)
    parser.add_argument("--timeout", type=int, default=1200)
    args = parser.parse_args()

    body_path = P / "geometry" / "front_body.npz"
    body_bytes = body_path.read_bytes()
    body_hash = hashlib.sha256(body_bytes).hexdigest()
    data = np.load(io.BytesIO(body_bytes))
    v, f = np.asarray(data["v"], dtype=float), np.asarray(data["f"], dtype=np.int32)
    config_dir, checks_dir = P / "print_config", P / "checks"
    config_dir.mkdir(exist_ok=True)
    checks_dir.mkdir(exist_ok=True)
    profiles, sources = {}, {}
    for kind, name in (("machine", args.machine), ("process", args.process), ("filament", args.filament)):
        profiles[kind], sources[kind] = full_profile(args.bambu_root, kind, name)

    machine, process, filament = (profiles[k] for k in ("machine", "process", "filament"))
    machine["printer_settings_id"] = args.machine
    # Current dual-extruder profiles declare defaults separately; the CLI also
    # needs the selected hotend volume in the full project configuration.
    machine["nozzle_volume_type"] = machine.get("default_nozzle_volume_type", ["Standard"])
    # Bambu uses the system printer name (or a user's inherits name) for its
    # compatibility check. Keep the unmodified machine identified as system;
    # identify our complete process as a user variant of the selected preset.
    process["name"] = args.process + " (Headset prop supports)"
    process["from"] = "user"
    process["inherits"] = args.process
    process["print_settings_id"] = process["name"]
    process.update({
        "enable_support": "1", "support_type": "tree(auto)",
        "support_on_build_plate_only": "0", "support_threshold_angle": str(args.support_angle),
        "support_top_z_distance": "0.2", "support_bottom_z_distance": "0.2",
        "brim_type": "outer_only", "brim_width": "5", "curr_bed_type": "Textured PEI Plate",
    })
    filament["filament_settings_id"] = [args.filament]
    filament["filament_colour"] = ["#A6A9AA"]
    config_paths = {}
    for kind, values in profiles.items():
        path = config_dir / (kind + ".json")
        path.write_text(json.dumps(values, indent=2, ensure_ascii=False), encoding="utf-8")
        config_paths[kind] = path

    bed = np.array([[float(n) for n in point.split("x")] for point in machine["printable_area"]])
    radians = math.radians(args.tilt_x)
    rot = np.array([[1, 0, 0], [0, math.cos(radians), -math.sin(radians)],
                    [0, math.sin(radians), math.cos(radians)]])
    posed = v @ rot.T
    translation = np.zeros(3)
    translation[:2] = (bed.min(0) + bed.max(0) - posed[:, :2].min(0) - posed[:, :2].max(0)) / 2
    translation[2] = -posed[:, 2].min()
    posed += translation
    bed_min, bed_max = bed.min(0), bed.max(0)
    height = float(machine["printable_height"])
    # Allow brim clearance as part of the geometric placement check.
    inside_bed = bool(np.all(posed[:, :2].min(0) - 5 >= bed_min) and
                      np.all(posed[:, :2].max(0) + 5 <= bed_max) and posed[:, 2].max() <= height)
    evidence = {
        "status": "running", "body_sha256": body_hash,
        "verifier_sha256": sha(Path(__file__)),
        "bambu_executable": str(args.bambu_root / "bambu-studio.exe"),
        "bambu_executable_sha256": sha(args.bambu_root / "bambu-studio.exe"),
        "body_vertices": len(v), "body_faces": len(f),
        "printer_profile": args.machine, "process_profile": args.process, "filament_profile": args.filament,
        "configured_preset_source": "Bambu Studio selected preset names read on 2026-10-03; no account data retained.",
        "profile_sources": sources,
        "full_config_sha256": {kind: sha(path) for kind, path in config_paths.items()},
        "print_orientation": {"wearing_z_up": args.tilt_x == 0, "rotate_about_wearing_x_deg": args.tilt_x,
                              "rotation_matrix": rot.tolist(), "translation_mm": translation.tolist()},
        "print_bounds_xyz_mm": [posed.min(0).tolist(), posed.max(0).tolist()],
        "printable_area_xy_mm": bed.tolist(), "printable_height_mm": height,
        "fits_bed_with_5mm_brim": inside_bed,
        "support": {key: process[key] for key in ("enable_support", "support_type", "support_on_build_plate_only",
                    "support_threshold_angle", "support_top_z_distance", "support_bottom_z_distance", "brim_width")},
        "bed_type_for_slice_check": process["curr_bed_type"],
        "printed_objects": ["front_body"], "references_excluded": ["head", "camera", "retention_band", "rear", "battery", "straps"],
        "wearing_3mf_modified": False,
        "limitations": ["Slicing validates toolpaths and supports for the chosen profile; it does not prove printed strength, fit, support removal or physical retention."],
    }
    evidence_path = checks_dir / "print_check.json"
    evidence_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    if not inside_bed:
        evidence["status"] = "failed_bed_fit"
        evidence_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
        raise RuntimeError("Body and brim do not fit the configured print volume.")

    started = time.monotonic()
    print("Slicing actual one-piece front with " + args.machine + "; temporary files will be removed.", flush=True)
    with tempfile.TemporaryDirectory(prefix="headset_slice_", dir=P) as temporary:
        scratch = Path(temporary)
        stl_path = scratch / "front_print_pose.stl"
        binary_stl(stl_path, posed, f)
        cli_args = [str(args.bambu_root / "bambu-studio.exe"), "--load-settings",
                    str(config_paths["machine"]) + ";" + str(config_paths["process"]),
                    "--load-filaments", str(config_paths["filament"]),
                    "--curr-bed-type", process["curr_bed_type"], "--arrange", "0", "--orient", "0",
                    "--ensure-on-bed", "--slice", "0", "--debug", "2", "--mstpp", str(args.timeout),
                    "--outputdir", str(scratch), str(stl_path)]
        startup = subprocess.STARTUPINFO()
        startup.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startup.wShowWindow = subprocess.SW_HIDE
        try:
            # Execute Bambu's installed wrapper so its resource lookup resolves
            # the actual shaders and printer data beside the Bambu executable.
            # On Windows stdout may be empty; result.json is the engine report.
            result = subprocess.run(cli_args,
                                    capture_output=True, cwd=scratch, timeout=args.timeout + 60,
                                    startupinfo=startup, creationflags=subprocess.CREATE_NO_WINDOW)
            log = (result.stdout + result.stderr).decode("utf-8", errors="replace")
            evidence["cli_exit_code"] = result.returncode
            evidence["diagnostics"] = [line for line in log.splitlines()
                                       if any(word in line.lower() for word in ("warning", "error", "failed", "success", "version", "cli mode"))][-40:]
            evidence["cli_log_sha256"] = hashlib.sha256(result.stdout + result.stderr).hexdigest()
            result_path = scratch / "result.json"
            engine_result = json.loads(result_path.read_text(encoding="utf-8")) if result_path.exists() else {}
            evidence["engine_report"] = engine_result
            gcode = {}
            for path in scratch.rglob("*.gcode"):
                gcode[str(path.relative_to(scratch)).replace("\\", "/")] = parse_gcode(
                    path.read_bytes(), float(filament["filament_diameter"][0]), float(filament["filament_density"][0]))
            evidence["gcode_evidence"] = gcode
            evidence["inputs_unchanged_on_completion"] = sha(body_path) == body_hash
            evidence["status"] = "passed" if result.returncode == 0 and engine_result.get("return_code") == 0 and gcode and evidence["inputs_unchanged_on_completion"] else "failed"
            print(log[-12000:], flush=True)
        except subprocess.TimeoutExpired as exc:
            evidence["status"] = "timed_out"
            evidence["cli_exit_code"] = None
            evidence["timeout_seconds"] = args.timeout + 60
            evidence["diagnostics"] = ["Bambu CLI exceeded the configured slice timeout."]
            print(str(exc), flush=True)
    evidence["elapsed_seconds"] = round(time.monotonic() - started, 3)
    evidence["temporary_files_removed"] = True
    evidence_path.write_text(json.dumps(evidence, indent=2), encoding="utf-8")
    print("Slice check " + evidence["status"] + "; evidence: " + str(evidence_path), flush=True)
    return 0 if evidence["status"] == "passed" else 1


if __name__ == "__main__":
    sys.exit(main())
