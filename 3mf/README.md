# Complete 3D model generators

This folder contains the retained printed front, final rear, two-object handle,
all required source inputs and their generation code. Keep this folder together.
The desktop originals and former repository-root model directories are not
required. Installed dependencies are separate from the portable source set.

From the repository root, reproduce and verify all models with the local runtime:

```powershell
./3mf/.runtime/structural-runtime/Scripts/python.exe -B 3mf/regenerate.py --require-baseline
```

On another machine, use Python 3.11 and install the retained dependency versions:

```powershell
python -m pip install -r 3mf/requirements.txt
python 3mf/regenerate.py --require-baseline
```

Final model files:
- [Printed front](Headset_WOAD_Front_2026-10-03/camera_mount/Front_CS30_Mount_Print.3mf)
- [Printed rear](Headset_Rear/revised/Rear_Revised_Print_Ready.3mf)
- [Rear with head/battery references](Headset_Rear/revised/Rear_Revised_Wearing.3mf)
- [Two-object handle print project](Handle/Handle_Print.3mf)
- [PCB with U31-U45 and U48 socket models removed](PCB/3D_PCB1_5_2026-09-15_no_U31-U45_U48_headers.step)

The PCB STEP copy has its own [regeneration and verification instructions](PCB/README.md).

The original manual handle 3MF already has two model objects. Both are retained
with their original local meshes, component links, build transformations, assembly
metadata, printing settings and thumbnails. No new cut or inferred assembly pose
is introduced. The unchanged generated handle archive is byte-identical to the
supplied desktop `1.3mf`; the printed front is likewise byte-identical to its
supplied final source. Both geometries remain mesh-based because 3MF carries no
CAD construction history.

Entry points for later edits:
- Front: `Headset_WOAD_Front_2026-10-03/camera_mount/build.py`, `modify_front()`.
- Rear: `Headset_Rear/build.py` and `Headset_Rear/revised/build.py`.
- Handle: `Handle/build.py`, `modify_part()` for `housing` or `cover`, in each
  original native mesh coordinate frame (millimetres).

Front-only, rear-only and handle-only `regenerate.py` scripts live in the
corresponding folders. `--verify` validates edited front/handle meshes against
the generated outputs; `--require-baseline` also requires unchanged source
identity. The rear construction retains the original array-hash, topology,
contact-surface and preserved-region checks.

Required geometry inputs are in `Headset_Inputs`, `Headset_Rear/inputs` and
`Handle/inputs`. `requirements.txt` is shared. `.runtime` contains this machine's
reusable dependency environment and is excluded from Git; use its Python directly
or `python -m pip`, since moved virtual-environment launcher scripts may retain
their original installation paths. No existing intermediate is required.
Generated `geometry` and `checks` folders may be removed after running.
Digital identity confirms reproduction of the supplied data, not physical fit.
