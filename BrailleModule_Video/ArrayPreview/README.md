# Array preview and Cycles production rendering

`index.html` is the offline point-pattern editor and interactive preview. Final pictures and video come from **Cycles in `EnclosedArray.blend`**. Browser shadows, aperture shading and materials are preview approximations.

## Review status — 2026-10-09

Hsinlung has viewed these stills and judged the appearance insufficiently realistic. Raised and retracted dots are similarly bright, and the module top does not match the supplied physical references. The files below are retained for review, not approved production output. No full animation is approved.

The latest discussion proposes matching the photograph on one module first: camera and state, grazing directional light and ambient fill, separate retracted depth and raised exposure, then dot subsurface appearance and top-face shading. Fine texture follows those checks. This revision has not been implemented. A suggested −0.3 mm rest offset is an unmeasured trial value; shifting the whole existing animation would also lower its raised exposure.

`assets/textures/Plastic003/` retains Hsinlung's selected procedural material candidate, with its source, CC0 license and hashes. Its maps are not applied to the current scene. The unselected Plastic012A download was removed. See the repository's `CLAUDE.md` for the wider review handoff.

## Current stills

- `PinCloseup.png`: the browser's tactile-array preset, with the checker pattern.
- `SwitchPreview.png`: the browser's enclosed-switch preset.
- `EnclosureOverview.png`: the browser's whole-handle preset.

These replace the preceding browser screenshots: 1920 × 1080, 192 samples, environment lighting, depth of field and light monochrome grain. Revised stills require Hsinlung's acceptance before a full shot is rendered. No full animation has been rendered during this migration.

## Edit and render

Open `index.html`, edit or import a 10-row × 9-column sequence, then choose **导出 JSON**. The page is self-contained and needs no network. `launch.cmd` optionally serves it at `http://127.0.0.1:8867/`.

Run the retained runtime from the repository root:

```powershell
# Update the existing scene and render three review stills.
& '3mf/.runtime/structural-runtime/Scripts/python.exe' -B 'BrailleModule_Video/ArrayPreview/render_cycles.py' stills

# Import a newly exported browser sequence and rebuild the stills.
& '3mf/.runtime/structural-runtime/Scripts/python.exe' -B 'BrailleModule_Video/ArrayPreview/render_cycles.py' stills --sequence 'C:/path/frames.json'

# Only after still approval: render lossless 16-bit PNG sequences.
& '3mf/.runtime/structural-runtime/Scripts/python.exe' -B 'BrailleModule_Video/ArrayPreview/render_cycles.py' render

# Compose PNG sequences into H.264 MP4 with changing monochrome grain.
& '3mf/.runtime/structural-runtime/Scripts/python.exe' -B 'BrailleModule_Video/ArrayPreview/render_cycles.py' compose
```

`prepare` updates the existing scene without rendering. `verify` checks the saved animation. `--shot near|switch|whole|all` selects a shot; `--width`, `--height`, `--samples` control quality. `--frame` selects a still frame. `--fps` and `--tail` configure the timeline during preparation. Defaults: 1920 × 1080, 192 samples, 30 fps, one second after the final JSON command.

`assets/sequence.json` is the active sequence. The current five-frame sequence is exactly the browser's built-in demo: off, checker, cross, all on, off. The review still uses frame 46, 1.5 seconds into the sequence: 45 raised points at maintained height. This is an appearance demo, not an experiment log. Timestamps are milliseconds; the first timestamp becomes time zero. JSONL, a `{frames: [...]}` object, a single record and a single 10 × 9 matrix are also accepted.

Full shots write `frames/<shot>/frame_0001.png` onward. Composition writes `Array_near.mp4`, `Array_switch.mp4` and `Array_whole.mp4`. The Blender runtime includes the FFmpeg encoder; no separate installation is needed. Optional `--ffmpeg` selects an external encoder. The original PNGs remain unmodified during composition.

## Scene and material sources

The existing assembly is retained: 15 modules, 90 independently moving complete pins, the two original handle meshes and the bullet-head switch. Original vertices, topology, module placements and handle placements are preserved. Three-segment bevel modifiers round module edges by 0.06 mm and handle edges by 0.18 mm. Smaller shader bevels soften microscopic highlights.

Blender's bundled `interior.exr` is packed into the world, with one soft window light. The grey tabletop extends beyond the camera frustum. Module black plastic uses dielectric reflection with no metallic or emissive shading. `assets/textures/MouldDetail.png` is extracted from `../inputs/Touchpoint_Reference.jpg`: perspective correction, pin/rim masking and removal of broad lighting. Grayscale detail controls narrow roughness variation and microscopic bump rather than baking photographed highlights into the black colour. `../inputs/PhysicalMotionReference.mp4` is also the visual reference. The photograph has limited detail; this is an appearance reconstruction, not a measured PBR scan.

Ivory PLA printing detail keeps the browser's existing settings: 0.2 mm side layers, 0.42 mm diagonal top paths, 0.0035 mm side relief and 0.0014 mm top relief. These are visual settings. All image assets needed by Cycles are packed into the .blend.

The three cameras use `viewer3d.js` `setView` directions, bounds fitting and horizontal field of view, adapted to 16:9. Focus is on the tactile face, switch nose or device centre; apertures are f/22, f/32 and f/8. Motion blur uses a half-frame shutter. Cameras stay fixed; dot motion supplies motion blur.

## Motion and mapping

`assets/motion.json` is the shared source: 0.7 mm peak, 0.45 mm hold, 33.333 ms rise, 66.667 ms peak pause, 50 ms settle and 50 ms retraction. These remain provisional visual settings informed by the supplied 30 fps clip. Fractional linear keyframes preserve short stages and let Cycles evaluate shutter subframes. Repeated identical commands leave an ongoing stroke alone. Mid-stroke commands reverse from the current height.

M1–M15 go left to right, then top to bottom. Each module's upper row is dots 3/2/1 and lower row is 6/5/4. The PCB arrangement stays three columns by five rows: approximately 11 mm horizontal and 6.5 mm vertical centre spacing, including the first column's 0.127 mm offset.

`CyclesVerification.json` records mesh preservation, references, cameras and animation checks. Motion is compared directly against the actual `controls.js` function, including mid-stroke reversals; all 90 saved animations are checked at fractional frames. This verifies migration and timing, not perceptual realism or manufacturing fit.

## Geometry and browser maintenance

`ModuleArray.blend`, `build_array.py` and `surface_finish.py` retain the source array. `build_enclosure.py` is only for an intentional geometry rebuild; it reapplies production materials and animation after exporting the preview GLB. Routine appearance or sequence changes use `render_cycles.py` on the existing scene.

The enclosure source stays `../../3mf/Handle/inputs/Handle_Original.3mf`, with 71,860 housing and 670 cover triangles. STEP offsets recover the assembly frame. The 30.7 mm array translation, original slots and 90 crown clearances are retained; see `EnclosureVerification.json`. These checks do not establish PCB mounting fit.

The switch retains the user-directed 20 mm height excluding terminals, and smooth 4.2 mm wide, 2.6 mm high bullet nose. Its tip stays 1.2 mm above the faceplate; it differs from the BOM's 25 mm TSA06131 variant. It is static and does not control BLE. Dimension provenance remains in `SwitchVerification.json` and `../inputs/Khon_TSA06131_Reference.pdf`.

Browser sources are `viewer3d.js`, `controls.js` and `index.template.html`. Run `npm run build` to regenerate the self-contained HTML. Dependencies remain pinned, with licenses in `vendor/`. The page has no real-hardware control.

When only the template, JSON or preview GLB changes, `node build_web.mjs --page-only` reuses the existing viewer bundle and updates the embedded page assets.
