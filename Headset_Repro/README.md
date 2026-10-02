# Headset regeneration handoff

Run from the GitHub repository root. Python **3.11.15** was used; install:

```sh
python -m pip install -r Headset_Repro/requirements-lock.txt
```

The requested 72.02/20.55 cm³ version is retained independently of the later
review changes. These two commands start with raw inputs and rebuild all meshes
they consume; they do not copy cached NPZ or finished 3MF files:

```sh
python Headset_Repro/build.py front
python Headset_Repro/build.py rear
```

Outputs: `Headset_Repro/generated/requested/Front_Compact_Review_Wearing.3mf`
and `Rear_Carbon6K_FlatBase_Review_Wearing.3mf`. Both contain the shell in wearing
coordinates, without print rotation. The adjacent verification JSON gives volume
and bounds. `.build/headset_requested_<part>/` contains the entire generated
intermediate chain and the reproduced head registration record.

To regenerate the final newer review assemblies, use:

```sh
python Headset_Repro/build.py front --version latest
python Headset_Repro/build.py rear --version latest
```

These include the separate head and camera/battery reference objects. Their different dimensions are
reported separately; the requested original version is never changed to match
the newer review. Latest review assembly exporters can additionally include the
head and device reference objects; compare **shell volume**, not the sum of all
assembly objects. Latest outputs are under `Headset_Repro/generated/latest/`.

## Clean-copy results

| Version / shell | Volume cm³ | X × Y × Z mm |
|---|---:|---|
| Requested front | 72.0247816664 | 142.3133012831 × 196.0941261766 × 57.1400000006 |
| Requested rear | 20.5475161495 | 95 × 35.4000000030 × 29.7000000030 |
| Final newer front | 69.2837150465 | 142.3133012831 × 192.8875940013 × 57.1400000006 |
| Final newer rear | 19.9883319262 | 95 × 35.4000000030 × 32.0000000030 |

Both requested-version NPZ hashes exactly match the original handoff meshes.
Both newer-version NPZ hashes and the full 3MF model XML exactly match the
final delivered review directories. ZIP timestamps can change container hashes.
These runs used an empty build directory and a new venv populated by pip,
without system site packages, with Python's isolated mode enabled.

## Folders

| Folder | Contents |
|---|---|
| `Headset_Repro/raw/` | Original BTTF 3MF, both CS30 STEP references, actual Medium STL, source PDF, input hashes and dimensions/registration provenance |
| `Headset_Repro/history/` | Recovered earlier generation, inspection and rendering scripts, preserving their stage names; these are historical sources, not alternative approved designs |
| `Headset_Repro/versions/` | Exact historical generators for the explicitly requested 72.02/20.55 cm³ version |
| `Headset_Repro/verification/` | Clean-copy runs, actual measurements, package inventory and checks freshness records |
| `Headset_CompactFront_Review_2026-10-02/inputs/` | Preserved front intermediates and the STEP actually used for optical measurements |
| `Headset_Carbon6K_FlatBase_Review_2026-10-02/inputs/` | Preserved registered head, display head and earlier curved rear tray/fill; helper scripts |
| Each review's `geometry/` | Current shell generator plus its derived meshes and numerical construction records |
| Each review's `audit/` | Clearance, thickness, insertion/removal, collision and print-orientation scripts plus their most recent saved results |
| Each review's root | Wearing 3MF deliverables, images, measurement notes and export/render scripts |

Historical scripts use stage-relative input locations. `build.py` creates those
locations automatically for the active generation chain; the history folder
alone is not a promise that every superseded stage can run without its old
nonessential assets. The two documented commands are the verified entry points.
No missing intermediate is silently synthesized or replaced with a fitted shape.

## Generation chain

1. `inspect_reference.py`: BTTF Normal object's exact build scales and mesh.
2. Raw Medium STL → native mesh → `register_head.py`: unchanged scale-1 pose.
3. `build_actual_face_limit.py`: actual original-triangle forward clipping solid.
4. `build_thin_front.py`: both wings, ear tabs, beveled window and diagnostic air
   volumes. Its preserved generators regenerate the front's earlier NPZ inputs.
5. Selected compact front generator → wearing shell export.
6. For rear: `rear_surface.py` + `build_rear_tray.py` +
   `assemble_rear_preview.py` regenerate the earlier curved tray, two surfaces
   and fill. The selected rear generator cuts/joins these → wearing shell export.

The camera enclosure envelope and battery envelope use recorded dimensions.
STEP optical-measurement scripts are included separately; they do not replace
the finished-camera envelope with the bounds of the internal assembly.

## Coordinates and checks

All modeling units are **mm**. X is lateral, Y points posteriorly, Z points up.
BTTF center front face is Y=0 and its lower edge is Z=0. Native-to-wearing head
matrix and original mesh translation are in `raw/sources.md`. Camera tilt is 20°
downward; exact transforms are retained in each generator's numerical JSON.
Battery axis is X, cylinder Ø22.8 × 90.4 mm, source is the user's instruction.

Numerical audit scripts can be rerun on regenerated current meshes under
`.build/headset_latest_rear/`. For example, run each review's `audit/check_solids.py`
or `audit/audit_solids.py` with Python. The rear command generates both parts,
so cross-part checks have their required files. Exact available script names are
listed in the package inventory. Some thickness and surface-distance checks take
longer. Do not turn sampled thickness, a print orientation analysis, or a beam
strain estimate into a physical printing/assembly certification.

Image rendering is optional (`requirements-render.txt`); it uses bpy 4.5.3.
Windows font paths have been replaced with Pillow's bundled font. This affects
annotation appearance only. No rendering dependency is required for generation.
Saved audit results with older source hashes remain clearly identified as
historical, rather than treated as checks of the latest mesh.
Superseded check results removed by the modeling task are retained separately
under `history/results/`; the current eight saved numerical reports are indexed
in `verification/check_results_index.json`. No required geometry-input generator
is missing. The original generator/capture for `inputs/camera_source_front.png`
was not found; the preserved image is not needed by either generation command.
