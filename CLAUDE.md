# Review handoff for Claude — 2026-10-09

Hsinlung wants the recent work reviewed. Begin with the PCB drafts and Cycles appearance below; report findings before implementing a new direction. Address him as Hsinlung. Keep observations, calculations and unverified assumptions distinct. Repository background is in [README.md](README.md).

## Read first

- [PCB revision package](PCB_REDESIGN_2026-10-08/README.txt), its native schematic/PCB files, five schematic images, two placement images and `validation.json`.
- [Manufactured-board audit](3mf/PCB/PCB_PREPOWER_REVIEW_2026-10-07.md): September 15 copper, electrical limits, firmware compatibility and proposed measurements.
- [Array rendering](BrailleModule_Video/ArrayPreview/README.md), `render_cycles.py`, `EnclosedArray.blend`, `CyclesVerification.json` and the three PNG review stills.
- [Physical visual references](BrailleModule_Video/inputs/): supplied photograph, module PDF and `PhysicalMotionReference.mp4`.
- [Portable model sources](3mf/README.md). Commit `6f46dfa` already consolidated these sources and added the module/preview models; this handoff includes that recent context.

## PCB: latest drafts need correction

The manufactured PCB1_5 and the October redesign are separate evidence. The former has narrow high-current routes, including approximately 0.18 mm on U49 SW to L1. Digital connectivity checks did not establish current capacity. The latest conversation says the manufactured board has no tactile modules and is intended for testing while a replacement is considered. Do not present thermal estimates as measurements or certification.

The October 8 cloud source produced a five-page `Revised_Schematic.epro`, `Actual_Placement.epro2` (191.7065 × 35.7505 mm) and `Test98_Placement.epro2` (98 × 98 mm). Both drafts have 179 components and 1062 connected pin assignments. They are separate saved copies; original PCB1_5 remains. Neither draft has routing or copper pours. Six layers remain: Inner1 GND, Inner4 VCC, four routing layers. Q1's four footprint vias are retained.

Changes include 47 kΩ SER/SRCLK/RCLK pull-downs R40/R41/R42 and optional J_NTC. R22 remains 51 kΩ, with temperature detection disabled; the proposed 100 kΩ/B4100 sensor option would also need R22 changed to 82 kΩ. It is not fitted by default. U48, SW1, J_test and J_NTC retain pads but are excluded from the BOM. The 16-stage HC595/ULN chain, 15 working modules and existing power/gating architecture remain.

The actual-board draft preserves fixed U31–U45/U48 poses and the board outline; ESP sockets keep 25.4 mm spacing. ESP and sockets were rotated together to put the antenna beyond the end. These facts do not establish a practical layout.

**The October 9 follow-up review withdrew the earlier claim that layout optimization was complete. Both boards are drafts needing correction before routing.** It reported:

- U49 feedback-connected R7/R8 pads approximately 9.6/11.5 mm from FB, on the wrong side for a compact feedback arrangement; both drafts reuse this arrangement.
- J1 USB to U53 charger centre distances approximately 53 mm on the actual board and 68 mm on the test board. Review the charging path and local placement.
- Test-board U50/L2 and other power parts remain under ESP, restricting probing, observation and repair despite the larger board.
- ESP underside clearance of at least 4 mm has not been confirmed. Actual module-socket selection, insertion space, screw heads and standoffs are also unresolved. Do not assume ordinary 2.54 mm sockets fit the tactile module.

These are prior inspection findings for Claude to independently check against the files. `validation.json` records net, export and selected geometric checks. Native PCB DRC did not return; no load, temperature, loop or BLE measurements validate these drafts. Empty mismatch lists do not prove physical assembly or power-routing suitability.

Firmware was not changed. The pre-power audit identifies GPIO9/OE polarity and startup-latch ordering incompatibility, and the extra 16th shift stage under the current 15-byte protocol. Review those pending adaptations separately from the schematic; do not claim the new pull-downs resolve them. Preserve U48 as optional. Supplier budgets are 0.17 A per coil (15 groups: 15.3 A on VCC) and approximately 0.08–0.10 A per SMA. These are output-load budgets, not battery current or measured performance.

## Array: pipeline migrated, appearance rejected

The browser remains the offline 10 × 9 point-pattern editor and JSON exporter. Production pictures/video now use Cycles in the existing `EnclosedArray.blend`; 90 independent dot animations use `assets/sequence.json` and `assets/motion.json`. Mesh geometry and assembly placement were retained. Three 1920 × 1080, 16-bit PNG stills replace the older browser JPEGs. The current demo is off/checker/cross/all-on/off, not experiment data. No full array video was rendered.

Implemented: packed Blender `interior.exr`, soft window lighting, small edge bevels, PLA print texture, photo-derived `MouldDetail.png`, three camera presets, depth of field, motion blur and grain composition. Verification records animation agreement with browser controls, geometry preservation and a synthetic encoding check. It does not prove realism. `WebVerification.json` explicitly records that no new interactive browser test accompanied this migration.

Hsinlung viewed the result and judged it poor. Raised and retracted dots remain similarly bright; the top looks unlike the physical reference. In the latest discussion, Claude's single-module lighting comparison led to this revised proposed order:

1. Match the photograph's camera, pose and dot state on one module.
2. Match grazing directional light and weaker ambient fill before prioritizing fine texture.
3. Check retracted depth and raised exposure separately; do not shift the whole motion curve down. −0.3 mm is a trial hypothesis, not a measured dimension.
4. Compare dot subsurface appearance and matte, mottled top-face shading independently.
5. Add fine texture only after the state-dependent light/shadow relationship works; then transfer to the array and compare motion against the real video.

This correction was discussed only. It is not applied in the committed scene. Hsinlung selected ambientCG Plastic003 as a material starting point; its four maps and CC0/source/hash record remain in `assets/textures/Plastic003/`. It is procedural, not a measured material scan, and is not connected to the current scene. The unselected Plastic012A download was removed. Neither the precise shell/dot polymer nor proposed optical settings are established from the photograph.

Keep edits in the existing folder. Do not rebuild the assembly, create dated iterations or render a full shot before Hsinlung accepts the stills. Review the actual images against the references, rather than treating successful Blender checks as approval.

## Other recent work and environment

- `3mf/` retains front, rear and two-part handle inputs, final files, generators and readback verification. Digital reproduction does not prove physical fit. Do not restore the superseded root model folders.
- `BrailleModule/` is the separate static exterior model; `BrailleModule_Video/` retains the visual/motion sources. Their unmarked geometric details and timing remain estimates. Do not merge or delete these intentional source sets as duplicates.
- The experiment path remains `visionss/experiment_server.py`, shared by spatial and single-point conditions. Logs are ignored; firmware is still V2.8. See the respective READMEs and [TOPDOWN_VALIDATION.md](TOPDOWN_VALIDATION.md) for historical offline evidence. No new camera or experimental validation is implied by this handoff.
- Vision uses `D:/anaconda/envs/LING/python.exe`. The old lowercase `lingtouch` environment has broken NumPy/LAPACK. Modelling uses `3mf/.runtime/structural-runtime/Scripts/python.exe`; on another machine install the pinned modelling/module requirements. Do not commit the runtime.
- `pics/`, `Depth-Anything-V2/`, weights, experiment logs, secrets, dependencies, paper materials and local archives remain outside Git. Preserve those original datasets and user work. Do not update the global collaboration contract or local AGENTS memo unless asked.
