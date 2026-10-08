# Module motion preview

Run `launch.cmd`, then open <http://127.0.0.1:8866/> in Chrome or Edge. If the
preview is already running, open that address directly. The launcher uses the
existing project Python runtime and serves this folder on the local computer.

Click the picture to focus it, then press **1–6** or the corresponding numeric
keypad keys. Each key controls its own dot: retracted → higher peak → lower
maintained position. Press the same key again to retract it. The six buttons
provide the same controls. **全部收回** retracts all dots; **显示编号** identifies
their positions. Held keys do not repeatedly toggle a dot.

The current visual settings are:

| Stage | Height / duration |
| --- | --- |
| Retracted | 0 mm |
| Rise | 33 ms, reaching 0.70 mm |
| High peak pause | 67 ms |
| Settle | 50 ms, reaching 0.45 mm |
| Maintained | 0.45 mm, until toggled off |
| Retract | 50 ms |

These heights and timings are provisional preview choices, not measured
manufacturer specifications. The three-stage behavior follows Hsinlung's
requirement. Both the browser and Blender scene read the same
`assets/motion.json` profile and use firm linear strokes, followed by a stable
hold. The fixed-camera preview uses actual 3D-rendered height samples
from the approved photographic scene, including changing occlusion, shadows,
and highlights. It displays one nearest rendered height per frame to retain a
single sharp moving contour. The dots lift along their axes without elastic
wobble. The six pins now use one neutral grey-white finish for the complete
round head and straight shaft, with a small smooth join instead of a sharp
shading boundary. Their camera-visible body colour is kept uniform following
Hsinlung's correction. The photographic lighting and housing remain intact.

`build_appearance.py` creates `AppearanceStudy.blend` from the archived
photographic setup; `build_motion.py` adds the existing motion to this corrected
appearance. `render_assets.py` renders the corresponding preview poses.

The approved static scene is archived in
`../Archives/PhotoStudy_2026-10-07/`, including `ReferenceStudy.blend` and its
photographic previews. The source `../PhotoStudy/` remains available.

`ModuleMotion.blend` contains the editable 3D scene and a 60 fps sample timeline
(frames 1–430): each dot rises in turn, all remain raised, then all retract.
Select the root object **BrailleModule** to find `Dot_1_height_mm` through
`Dot_6_height_mm` under Object Properties → Custom Properties. Their animation
curves can be adjusted in the Graph Editor; timeline playback applies the
existing height keys. The browser provides the live keyboard controls.

The [user-provided Dot Pad video](https://www.youtube.com/watch?v=iSmRM2PUBzA)
was inspected around 6–8 seconds for axial movement and changing hole
occlusion. Revision 2 primarily follows Hsinlung's supplied physical-module
video (`../inputs/PhysicalMotionReference.mp4`, 11.4 seconds, 30 fps). In that
clip, lift is visible between frames
69–70 (2.300–2.333 s) and 256–258 (8.533–8.600 s); release is visible between
frames 300–302 (10.000–10.067 s). These observations support short strokes
and firm stops. Camera movement, compression, and the frame rate prevent
precise measurement of the high-to-maintained drop. Its height difference and
timing remain provisional choices for the requested three-stage effect.
