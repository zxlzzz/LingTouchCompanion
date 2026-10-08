# Retained front and rear

This directory is part of the complete `3mf` source set. See [../README.md](../README.md)
for dependency setup, all final outputs and the combined regeneration command.
From the repository root:

```powershell
python 3mf/Headset_WOAD_Front_2026-10-03/regenerate.py --require-baseline
```

This rebuilds the retained rear and the actual printed front. Front-only entry:
`camera_mount/regenerate.py`. The front is edited through `modify_front()` in
`camera_mount/build.py`; it uses the source print axes with bed centre
(165, 160, 0) removed. The immutable finished front archive is retained in
`../Headset_Inputs/Front_CS30_Mount_Final.3mf`.

The unchanged front archive is reproduced byte for byte. Old camera/head fit
assemblies are not reused. The rear uses the anatomical tray/fill inputs in
`../Headset_Rear/inputs`, its construction scripts and provenance. Its wearing
reference also requires the original head STL and registration in
`../Headset_Inputs`. No deleted file or desktop original is required.
