# Retained headset models

Final front: `camera_mount/Front_CS30_Mount_Print.3mf` (printing) and
`camera_mount/Front_CS30_Mount_Wearing.3mf` (fit references).
Final rear: `../Headset_Rear/revised/Rear_Revised_Print_Ready.3mf` and
`../Headset_Rear/revised/Rear_Revised_Wearing.3mf`.

For a new machine or Claude workspace, use Python 3.11. From the repository
root, create and activate a virtual environment, then run:

```powershell
python -m pip install -r Headset_WOAD_Front_2026-10-03/requirements.txt
python Headset_WOAD_Front_2026-10-03/regenerate.py
```

The normal build uses the retained converted camera inputs. `--rebuild-inputs`
also retessellates the original customer STEP using `cadquery-ocp`.
Optional `--verify`, `--render`, and `--slice` operate on the final front;
slicing requires the installed Bambu Studio engine.

Front-only entry: `camera_mount/regenerate.py`. Rear-only entry:
`../Headset_Rear/regenerate.py`. Each rebuilds its prerequisites.

`build.py`, `revised/build.py`, and `structural/build.py` are the required
geometry construction stages. Their intermediate meshes are dependencies,
not alternative deliverables. `printable/export.py`, `onepiece/evaluate.py`,
`print_check.py`, `render.py`, and `checks/*.py` supply shared helper functions.
The original camera STEP, head STL, registration, BTTF reference, and source
manifests remain in `../Headset_Inputs`. The final print settings are stored
in `camera_mount/project_settings.json` and `project_metadata.json`.

Cleanup preserves the final model geometry and saved printing settings.
Digital generation and slicing do not establish physical fit or strength.

## Files to upload and edit

Upload the three `Headset_*` directories as selected by Git. `.gitignore`
excludes the local Python environment, regenerated meshes, check results and
rendered previews. Original inputs, conversion code, dependencies, settings
and the four final 3MF files remain included. The build recreates excluded
intermediates; no machine-specific environment directory is needed.

For front changes, edit `camera_mount/build.py` (camera slot),
`structural/build.py` (shell and temples), or `revised/build.py` (nose support)
as appropriate. Shared geometric primitives live in `build.py`. For the
final rear, edit `../Headset_Rear/revised/build.py`; its base construction is
in `../Headset_Rear/build.py`. Run the regeneration entry point after editing.
