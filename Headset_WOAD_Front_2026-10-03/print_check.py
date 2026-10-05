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
DEFAULT_MACHINE = "Bambu Lab H2C 0.4 nozzle"
DEFAULT_PROCESS = "0.20mm Standard @BBL H2C"
DEFAULT_FILAMENT = "Bambu PLA Basic @BBL H2C"


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


def bed_contact(v, f):
    """Measure real triangles on the lowest plane, including patch continuity."""
    tri = v[f]
    z = tri[:, :, 2]
    lowest = float(v[:, 2].min())
    mask = (np.ptp(z, axis=1) < 1e-5) & (np.abs(z.mean(axis=1) - lowest) < 1e-5)
    flat = f[mask]
    areas = np.linalg.norm(np.cross(tri[mask, 1] - tri[mask, 0],
                                   tri[mask, 2] - tri[mask, 0]), axis=1) / 2
    parents = np.arange(len(flat))
    edges = {}
    def find(i):
        while parents[i] != i:
            parents[i] = parents[parents[i]]
            i = parents[i]
        return i
    for i, triangle in enumerate(flat):
        for a, b in ((triangle[0], triangle[1]), (triangle[1], triangle[2]), (triangle[2], triangle[0])):
            edge = tuple(sorted((int(a), int(b))))
            if edge in edges:
                parents[find(i)] = find(edges[edge])
            else:
                edges[edge] = i
    patches = {}
    for i, area in enumerate(areas):
        root = int(find(i))
        patches[root] = patches.get(root, 0.0) + float(area)
    return {"triangle_count": int(mask.sum()), "total_area_mm2": float(areas.sum()),
            "edge_connected_patch_areas_mm2": sorted(patches.values(), reverse=True),
            "single_continuous_patch": len(patches) == 1,
            "max_planarity_error_mm": float(np.ptp(z[mask])) if mask.any() else None,
            "method": "Actual mesh triangles at minimum print Z, tolerance 0.00001 mm; shared-edge connectivity."}


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


