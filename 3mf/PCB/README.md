# PCB STEP with module sockets removed

Use `3D_PCB1_5_2026-09-15_no_U31-U45_U48_headers.step` for the modified PCB assembly.
The original 2026-09-15 export is retained unchanged under `inputs/`.

Only the 16 female socket models at U31-U45 and U48 are removed. U46 and U47
are chips in this export and remain unchanged. PCB copper, holes,
other components, colours and placements are preserved.

Regenerate from the repository root:

```powershell
python 3mf/PCB/remove_module_headers.py
```

The generator requires only Python's standard library. To repeat the CAD check,
install `cadquery-ocp==8.0.1.1.0` and run with `--verify`. This machine already
has that dependency in `3mf/.runtime/structural-runtime`.

Verification requires the original source SHA256, validates all STEP references,
and checks that all retained entity records except the root placement list are
byte-identical. The unused shared socket definition is also removed to prevent
it from appearing as an unattached object. CAD import confirms 179 to 163 top-level objects,
with unchanged solid/face/edge counts, volumes, centres and bounds for every
retained object. This edit changes the exported 3D assembly only.
