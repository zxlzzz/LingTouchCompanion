# Braille module - static exterior model

This folder is independent of `3mf/`. The model follows the supplied module PDF
and Hsinlung's material instructions: a black housing and slightly grey white
tactile dots. It includes the housing, lower collar/carrier, locating tab,
twelve stamped terminals and six individually named dots.

## Files

- `BrailleModule.blend`: editable Blender 4.5 scene, materials and preview lighting.
- `BrailleModule.glb`: portable model with materials and separate parts; no studio objects.
- `BrailleModule.step`: millimetre CAD assembly with the same parts and colours.
- `Preview.png`, `Preview_Back.png`, `Preview_Top.png`, `Preview_Dots.png`: rendered views.
- `parameters.json`, `build.py`, `requirements.txt`: retained editable generator.
- `inputs/Braille_Module_Reference.pdf`: unchanged supplied reference.
- `inputs/Touchpoint_Reference.jpg`: supplied physical-module photograph.
- `Verification.json`: geometry, dimensions and export readback checks.

## Dimensions and interpretation

The PDF explicitly dimensions the body as 8.2 x 6 mm, with a height of 20 mm
excluding the terminals. The maximum base width is 10.82 mm, including the
asymmetric tab. Terminals extend 3.8 mm below the base. Their pitch is 1.25 mm,
tail width 0.30 mm and sheet thickness 0.10 mm. The 4.96 mm drawing dimension
spans the inner faces of the two terminal sheets, giving 5.06 mm centre spacing.
The two rows use the 2.05 and 2.65 mm opposite-view end offsets and are staggered.

Unmarked dimensions, including dot diameter/pitch, recesses, collar height and
terminal shoulders, are reconstructed from drawing proportions. Shell wall and
cap thickness are visual construction choices. These are recorded separately
from dimensioned values in `parameters.json`. The interior actuator mechanism
is not established by this document and has not been invented in the model.
Actual lower carrier colour and plating appearance remain unverified.

All six dots have spherical-cap heads, matching the curved tips in the PDF
and the two raised points in the supplied photograph. The former flat-topped
visible cylinders have been replaced. The 0.45 mm cap height is an exterior
estimate, not an explicitly dimensioned value: the PDF's 0.4-0.5 mm figure is
the raised-point height above the housing. Cap diameter and dot spacing retain
the initial model values. Housing, base, terminals, positions and materials
remain unchanged.

All six dots are in the same retracted static state, with their apices flush
with the 20 mm tactile face and their curved sides inside the openings. There
are no keyframes or raised-dot states. In a top view with the locating tab at the top, dots 1/2/3
form the left column and 4/5/6 the right column, following PDF page 6. Each dot
has its own origin and can later move along its local +Z axis. Terminal names
`Pin_01` through `Pin_12` are geometry indices, not a verified electrical map.

Blender and GLB store metre coordinates, with Blender displaying millimetres.
STEP uses millimetres. The overall assembly is 10.82 x 6 x 23.8 mm.

## Regenerate

On this machine, from the repository root:

```powershell
& '3mf/.runtime/structural-runtime/Scripts/python.exe' -B 'BrailleModule/build.py'
```

This uses the existing modelling runtime without writing model outputs into
`3mf/`. On another machine, install `requirements.txt` in a Python 3.11
environment and run `python -B build.py`. `--no-render` skips the preview images.

Verification checks each CAD solid and tessellated mesh, reloads the STEP/GLB,
checks the overall dimensions and ensures all six dot apices remain flush. It does
not establish exact agreement of unmarked details with the physical module.
