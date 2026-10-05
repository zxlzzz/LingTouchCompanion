"""Read-only orientation experiments using the user's saved Bambu settings.

The preserved revised body is posed numerically and sliced sequentially by
the installed hidden Bambu CLI. Temporary meshes/configuration/G-code are
removed. No delivered 3MF, body geometry or user setting is changed.
"""
from pathlib import Path
import argparse
import hashlib
import importlib.util
import io
import json
import math
import re
import subprocess
import tempfile
import time
import zipfile

import numpy as np
from scipy import ndimage

P = Path(__file__).resolve().parent
BASE = P.parent


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def actual_profiles(methods, engine_root, settings):
    names = {"machine": settings["printer_settings_id"],
             "process": settings["print_settings_id"],
             "filament": settings["filament_settings_id"][0]}
    profiles, provenance = {}, {}
    for kind, name in names.items():
        profiles[kind], provenance[kind] = methods.full_profile(engine_root, kind, name)
    original_keys = {kind: set(values) for kind, values in profiles.items()}
    # A saved project also contains UI bookkeeping and fields whose project
    # representation is invalid inside preset files. Native profile keys plus
    # these established CLI keys are the supported preset overlay boundary.
    extra_keys = {"machine": {"nozzle_volume_type"},
                  "process": {"brim_type", "curr_bed_type"},
                  "filament": {"filament_colour"}}
    assignments = {}
    for key, value in settings.items():
        if key in ("name", "from", "type", "instantiation", "inherits", "setting_id"):
            continue
        kinds = [kind for kind in profiles if key in original_keys[kind] or key in extra_keys[kind]]
        if not kinds:
            continue
        for kind in kinds:
            profiles[kind][key] = value
        assignments[key] = kinds
    profiles["machine"]["printer_settings_id"] = names["machine"]
    profiles["process"].update({"name": names["process"] + " (Actual settings orientation check)",
        "from": "user", "inherits": names["process"],
        "print_settings_id": names["process"] + " (Actual settings orientation check)"})
    profiles["filament"]["filament_settings_id"] = settings["filament_settings_id"]
    # All slicing-relevant saved settings must survive into an effective profile.
    assert all(any(profiles[kind].get(key) == value for kind in assignments[key])
               for key, value in settings.items() if key in assignments and key != "print_settings_id")
    return profiles, names, provenance, assignments, sorted(set(settings) - set(assignments))


def first_layer_evidence(raw, settings):
    """Inspect actual positive extrusion on the first layer, excluding start G-code.

    Raster area is a union of nominal-width extrusion strokes, not a claim
    about real adhesion. Actual centerlines and G2/G3 arc sweeps are retained
    internally only while calculating the compact first-layer evidence.
    """
    height = float(settings["initial_layer_print_height"])
    initial_width = float(settings["initial_layer_line_width"])
    filament_area = math.pi * (float(settings["filament_diameter"][0]) / 2) ** 2
    xyz = np.zeros(3)
    absolute_xyz, absolute_e, last_e = True, False, 0.0
    role, width, first_seen = "Custom", initial_width, False
    token = re.compile(r"([XYZERIJ])([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)")
    paths, strokes = {}, {}
    for line in raw.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith(("; FEATURE:", "; TYPE:")):
            role = line.split(":", 1)[1].strip()
        wm = re.match(r";\s*LINE_WIDTH:\s*([\d.]+)", line)
        if wm:
            width = float(wm.group(1))
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
            amount = values.get("E", last_e if absolute_e else 0.0)
            if absolute_e:
                amount -= last_e
                if "E" in values:
                    last_e = values["E"]
            if (first_seen and amount > 0 and role != "Custom"
                    and any(k in values for k in "XY") and xyz[2] > height + 1e-4):
                break
            if (amount <= 0 or role == "Custom" or not any(k in values for k in "XY")
                    or abs(float(xyz[2]) - height) > 1e-4):
                continue
            first_seen = True
            points = [old[:2], xyz[:2].copy()]
            if line.startswith(("G2 ", "G3 ")) and ("I" in values or "J" in values):
                center = old[:2] + [values.get("I", 0), values.get("J", 0)]
                radius = float(np.linalg.norm(old[:2] - center))
                start = math.atan2(old[1] - center[1], old[0] - center[0])
                end = math.atan2(xyz[1] - center[1], xyz[0] - center[0])
                clockwise = line.startswith("G2 ")
                sweep = ((start - end) if clockwise else (end - start)) % (2 * math.pi)
                if np.linalg.norm(xyz[:2] - old[:2]) < 1e-6:
                    sweep = 2 * math.pi
                angular_step = 2 * math.acos(max(-1, min(1, 1 - .005 / max(radius, .005))))
                count = max(2, math.ceil(sweep / max(angular_step, 1e-6)))
                angles = start + (-1 if clockwise else 1) * np.linspace(0, sweep, count + 1)
                points = center + radius * np.column_stack((np.cos(angles), np.sin(angles)))
            points = np.asarray(points)
            lengths = np.linalg.norm(np.diff(points, axis=0), axis=1)
            info = paths.setdefault(role, {"extrusion_mm": 0.0, "segments": 0,
                "path_length_mm": 0.0, "xy_min_mm": [math.inf, math.inf],
                "xy_max_mm": [-math.inf, -math.inf]})
            info["extrusion_mm"] += amount
            info["segments"] += 1
            info["path_length_mm"] += float(lengths.sum())
            info["xy_min_mm"] = np.minimum(info["xy_min_mm"], points.min(0)).tolist()
            info["xy_max_mm"] = np.maximum(info["xy_max_mm"], points.max(0)).tolist()
            strokes.setdefault(role, []).extend((a.copy(), b.copy(), width)
                for a, b in zip(points[:-1], points[1:]) if np.linalg.norm(b - a) > 1e-8)
    for info in paths.values():
        info["equivalent_deposited_area_mm2"] = round(info["extrusion_mm"] * filament_area / height, 3)
        info["extrusion_mm"] = round(info["extrusion_mm"], 3)
        info["path_length_mm"] = round(info["path_length_mm"], 3)

    model_roles = [k for k in strokes if k not in ("Support", "Support interface", "Brim", "Skirt", "Wipe tower")]
    groups = {"model": model_roles, "brim": ["Brim"], "support_foundation": ["Support", "Support interface"]}
    raster = {}
    step = .05
    for group, roles in groups.items():
        lines = [line for role_name in roles for line in strokes.get(role_name, [])]
        if not lines:
            raster[group] = {"area_mm2": 0.0, "patch_areas_mm2": []}
            continue
        low = np.min([np.minimum(a, b) - w / 2 for a, b, w in lines], axis=0) - step
        high = np.max([np.maximum(a, b) + w / 2 for a, b, w in lines], axis=0) + step
        nx, ny = np.ceil((high - low) / step).astype(int) + 1
        mask = np.zeros((ny, nx), dtype=bool)
        for a, b, w in lines:
            radius = w / 2
            imin = np.maximum(np.floor((np.minimum(a, b) - radius - low) / step).astype(int), 0)
            imax = np.minimum(np.ceil((np.maximum(a, b) + radius - low) / step).astype(int) + 1, [nx, ny])
            xs = low[0] + np.arange(imin[0], imax[0]) * step
            ys = low[1] + np.arange(imin[1], imax[1]) * step
            xx, yy = np.meshgrid(xs, ys)
            delta = b - a
            t = np.clip(((xx - a[0]) * delta[0] + (yy - a[1]) * delta[1]) / np.dot(delta, delta), 0, 1)
            hit = (xx - (a[0] + t * delta[0])) ** 2 + (yy - (a[1] + t * delta[1])) ** 2 <= radius ** 2
            mask[imin[1]:imax[1], imin[0]:imax[0]] |= hit
        labels, count = ndimage.label(mask, structure=np.ones((3, 3)))
        areas = np.bincount(labels.ravel())[1:] * step ** 2
        raster[group] = {"area_mm2": round(float(mask.sum() * step ** 2), 3),
            "patch_areas_mm2": [round(float(x), 3) for x in sorted(areas, reverse=True) if x >= .1],
            "connected_patch_count": int(count), "xy_bounds_mm": [low.tolist(), high.tolist()]}
    return {"z_mm": height, "features": paths, "raster_stroke_union": raster,
        "raster_grid_mm": step, "default_nominal_stroke_width_mm": initial_width,
        "area_method": "Union of actual first-layer positive-extrusion centerline strokes, using G-code LINE_WIDTH or initial-layer width; 0.05 mm raster, 0.005 mm arc chord tolerance. This approximates deposited footprint and does not measure physical adhesion.",
        "equivalent_area_method": "Positive E filament volume divided by first-layer height; includes path overlap and flow-ratio effects, so is not a union footprint."}


def support_height_bins(raw, settings):
    filament_area = math.pi * (float(settings["filament_diameter"][0]) / 2) ** 2
    density = float(settings["filament_density"][0])
    bins = {key: {"extrusion_mm": 0.0, "segments": 0} for key in ("0-10", "10-50", "50-100", "100+")}
    z, last_e, absolute_e, role = 0.0, 0.0, False, "Custom"
    token = re.compile(r"([ZE])([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)")
    for line in raw.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if line.startswith(("; FEATURE:", "; TYPE:")):
            role = line.split(":", 1)[1].strip()
        elif line.startswith("M82"):
            absolute_e = True
        elif line.startswith("M83"):
            absolute_e = False
        elif line.startswith("G92 "):
            values = {k: float(v) for k, v in token.findall(line.split(";", 1)[0])}
            if "E" in values:
                last_e = values["E"]
        elif line.startswith(("G0 ", "G1 ", "G2 ", "G3 ")):
            values = {k: float(v) for k, v in token.findall(line.split(";", 1)[0])}
            if "Z" in values:
                z = values["Z"]
            amount = values.get("E", last_e if absolute_e else 0.0)
            if absolute_e:
                amount -= last_e
                if "E" in values:
                    last_e = values["E"]
            if amount <= 0 or role not in ("Support", "Support interface") or not ("X" in line or "Y" in line):
                continue
            key = "0-10" if z < 10 else "10-50" if z < 50 else "50-100" if z < 100 else "100+"
            bins[key]["extrusion_mm"] += amount
            bins[key]["segments"] += 1
    for item in bins.values():
        item["mass_g"] = round(item["extrusion_mm"] * filament_area / 1000 * density, 3)
        item["extrusion_mm"] = round(item["extrusion_mm"], 3)
    return {"height_units": "printer Z mm", "features": ["Support", "Support interface"],
            "bins": bins, "method": "Actual positive XY extrusion classified by modal print Z; relative E or absolute E tracked. Saved project uses absolute XYZ."}


