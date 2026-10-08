# Photographic module study

One clean photographic material and lighting setup, with two camera views:

- `ReferenceStudy.png`: 1200 x 1600, composition based on the supplied physical-module photograph.
- `VideoCloseup.png`: 1920 x 1080, a closer horizontal view for assessing later video footage.
- `ReferenceStudy.blend`: editable, self-contained scene containing both cameras.
- `Verification.json`: geometry, source and render checks.
- `build.py`: reproducible scene setup.

The study uses the accepted model in `../BrailleModule.blend`. Its 22 component
meshes and local positions remain unchanged. All six dots stay retracted and
independent. There is no animation, dirt, wear or image compositing. The whole
assembly rests on its back broad face on a pale laminate table.

Clean moulded-polymer roughness and microrelief, grey-white smooth tactile
heads, directional lighting and the table's reflected light determine the
appearance. Perspective cameras and optical depth of field provide the two
views. The top's grey reflection does not represent a change to a metal shell.
These are appearance trials; single-image evidence does not establish the exact
physical material, roughness or lens of the reference.

References: the supplied `../inputs/Touchpoint_Reference.jpg`, the supplier PDF
for geometry, and [Dot Inc's supplied video](https://www.youtube.com/watch?v=iSmRM2PUBzA).
The video was inspected in the browser at 6, 12, 18, 25, 32, 45 and 51 seconds;
the low-angle view around 6 seconds was especially useful for surface highlights.
Dot Pad imagery informs photography only, not this module's design.

Rebuild from the repository root using the existing Blender runtime:

```powershell
& '3mf/.runtime/structural-runtime/Scripts/python.exe' -B 'BrailleModule_Video/PhotoStudy/build.py' --final
```

The original `BrailleModule/` and frozen parent-folder source files are preserved.
