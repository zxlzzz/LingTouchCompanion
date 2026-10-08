# PCB1_5 pre-power review — working notes, 2026-10-07

## Next work and current state

- Hsinlung wants to finish assembling and powering the already-manufactured board. No modules, battery, switches, USB connector or ESP are installed; the remaining SMT parts are reportedly soldered. An adjustable bench supply is available. No physical readings have been received.
- Read-only file checks are complete. Hsinlung explicitly corrected the task: identify this board's limits, obstacles, bottlenecks and practical measurements. Do not turn this into reinforcement, microscopic rework or a replacement PCB project. No repair is a prerequisite to controlled no-load bring-up.
- ESP sockets, SW2 and the USB connector can be soldered. Keep connector installation distinct from connecting a powered USB cable or adding loads during bring-up. The earlier blanket instruction to leave these connectors uninstalled was withdrawn.
- Hsinlung rejected the PDF delivery and requested Markdown for the assistant's own record. Explain findings directly in chat; do not make him read this note to obtain an answer.
- Preserve PCB, schematic, firmware, rules and placement. This audit has not changed them. Keep U48 optional/DNP. No solder repair or firmware edit has been carried out.
- Hsinlung supplied further context: two boards are available, and the module supplier's SMA current is approximately 0.08 A, maximum approximately 0.10 A each. Use this supplier budget (1.2–1.5 A for fifteen), while checking its operating conditions in the single-module test. Do not continue claiming the SMA current is wholly unknown or that fifteen SMAs inherently exceed U50's 3 A rating.
- The earlier real-module escalation plan is superseded by power-path screening with dummy loads before installing the full array. A test on board B is evidence about B and the common design; it does not automatically certify board A.

## Evidence and completed checks

Board UUID: `ee18a5fa84dcc341`, 175 components. Use the **September 15 manufacturing Gerber**, not the earlier unrouted `ProDoc` export. Source directory: `C:/Users/Hsinlung/Downloads`.

| Source | SHA256 |
| --- | --- |
| `ProPrj_test_2026-09-14.epro2` | `3baab5a5025d5d3e656917474c9268d36992920da064ea37aa99657b85bb309a` |
| `Gerber_PCB1_5_2026-09-15.zip` | `05ad356413c3d1ee96b63992e6b6c71dc4399a9aab90f99d8689a383c067296d` |
| `InteractiveBOM_PCB1_5_2026-9-15.html` | `292f6bc0e3b4db20478ce4d166884625133faa2de81a93843aaad90f1235474a` |
| `BOM_Board1_PCB1_5_2026-09-15.xlsx` | `835757f2a68c90db508c8f68d1df4ac0ef328deade753dd56c229a862f4b7fb9` |

- All 175 BOM designators, values and manufacturer part numbers match the project schematic. Evaluate tactile modules as custom interfaces; their borrowed BOM connector identity does not describe their function.
- The 298 circuit-net pin partitions match `Netlist_Schematic1_2026-09-12.tel` and the Gerber flying-probe export. Additional `NET_*` labels are artificial NC labels, not additional functional circuit nets.
- Six copper layers and plated drill connections were reconstructed geometrically and associated with component pads: **no missing pad copper, cross-net shorts or disconnected circuit nets found**. Duplicate exported drill records were not treated as extra parallel holes.
- Inner1 is GND and Inner4 is VCC. Both exported planes contain large continuous copper areas. Outer-layer minimum inter-net spacing was approximately 0.108 mm; the scan found no labeled inter-net copper gap below 0.105 mm.
- All 16 HC595/ULN/module groups were checked for supplies, ground, clocks, reset, OE, cascade and seven output connections.
- Geometry used approximately 0.5 µm arc approximation. These checks do not establish actual solder quality, complete native DRC/DFM compliance, current capacity, loop stability, temperature or RF performance. Original file hashes were rechecked unchanged.
- Temporary parsers, downloaded datasheets and analysis dependencies were cleaned up. The working note and measurement image remain.

## Findings that need practical resolution

### Power current paths

- U49 SW → L1 input carries inductor current through approximately **0.18 mm** copper. The VCC plane cannot bypass this different-net series path.
- A cold strip estimate is on the order of **20 mΩ** for the narrow SW route, using nominal 35 µm outer copper. This is not a full parallel-network resistance measurement, pulse-temperature calculation or allowable-current rating. Overlapping Gerber strokes occupy the same copper and are not doubled copper thickness. Do not use this number alone to demand rework or declare the board unusable.
- L1's VCC pad has no local plated-hole array. Copper must reach the plane through external traces/holes. Nearby VCC vias use approximately 0.312 mm drill diameter. Actual finished copper and hole-wall plating have not been measured.
- Battery input, 5 V converter and charger switching paths also contain 0.18/0.23 mm segments. Do not propose reinforcing only SW → L1 and then claim all other high-current paths are cleared.
- Use trace calculations only to select voltage-drop and temperature measurements. They do not establish a safe current limit or prove the board unusable. Reinforcement proposals were outside the requested direction and have been stopped.
- Regulated VCC remaining nominal does not establish low dissipation in the U49 SW-to-L1 series trace. The feedback loop can compensate a resistive loss while the trace heats. Voltage observations are useful for localization after regulation/delivery deteriorates; they are not advance protection against trace failure. Dummy-load screening must also include actual load-current confirmation and local temperature monitoring; absence of a burnt trace is not a sufficient pass criterion.
- Actual Gerber aperture orientation places L1's pad at 4 mm wide by 5 mm high in the top projection. The former 6.87 mm / 18.8 mΩ estimate used the wrong rectangular orientation and was withdrawn. The resistive narrow section is roughly 7–8 mm. A centerline-only subtraction gives 8.37 mm but counts a vertical segment touching the long U49 pad along its edge; this is not a full resistance solution. Avoid false precision from simplified graph models.
- Manufacturing copper includes routes different from the project export. Geometric net association found no cross-net label conflicts. USB VIN_C follows a long 0.18 mm path through internal routing layers; VCCS also follows long fine traces and has no supply plane. Exact network resistance was not established, so do not present shortest-path estimates as complete parallel-network or thermal results.

### SW trace adjacent-plane check and rough thermal estimate

- Latest request: check whether U49 pin20 → L1 has adjacent copper and roughly assess the quoted 30/36/50-coil thermal limits. This does not authorize rework or redesign.
- Both parts and the SW route are on Bottom. The immediately adjacent plane is Inner4 (physical copper layer 5), VCC, not the opposite-side Inner1 GND plane.
- In the target PCB document (`ee18a5fa84dcc341`), select current records by ticket, not the last historical occurrence in the whole EPRU. `LAYER_PHYS` dielectric365 is 3.913 mil = 0.0993902 mm, material 3313 RC57%. Inner4 copper is 0.598 mil = 15.1892 µm; outer copper is 1.378 mil ≈35 µm. These are CAD stack settings, not measured finished-board dimensions.
- Reconstructed manufacturing `Gerber_InnerLayer4.G4` dark-plane region minus clear antipads before isolated pad flashes. The largest connected VCC region is 5852.316 mm². Along the main SW centerline, no missing plane was found. Approximately 97.3% of the 0.18 mm route footprint outside the two large pads overlaps this connected plane. Three antipad circles clip the footprint edges near x=−4.02148, −2.83513 and +0.69276 mm; they do not cut across the route. Nearby plane copper exists; it is not an isolated island or a whole-length keepout. Diagram: `PCB_SW_INNER4_2026-10-07.png`, common TOP projection.
- Using roughly 20 mΩ cold strip resistance and 0.17 A per coil, 24/30/36/50/90 simultaneously active coils draw 4.08/5.10/6.12/8.50/15.30 A. Including nominal 2.31 A p-p inductor ripple gives approximately 0.35/0.54/0.77/1.47/4.75 W ON-time strip loss; 20% duty gives approximately 0.069/0.107/0.153/0.294/0.950 W average, before temperature-driven resistance increase.
- Exploratory strip/FR4 conduction sensitivity used FR4 k=0.25–0.4 W/(m K), copper k=385, FR4 volumetric heat capacity 1.8 MJ/(m³ K) as an assumed typical value, copper temperature coefficient 0.00393/K. With the adjacent plane held at 25°C and ignoring end-pad cooling, 200 ms / 1 Hz pulse hotspot rises were ~42–71 K at 24 coils, ~71–127 K at 30, ~115–221 K at 36. This is a deliberately simplified comparison, not calibrated full-board simulation. End pads reduce these rises; plane/IC/inductor heating and antipads can increase them. Changing copper thickness or actual coil current materially changes the result.
- An infinite-length-strip/full-cross-section model substantially overstates the whole-plane steady heating for this short route; its numerical temperatures were discarded. At high temperatures all linear models also become invalid; their runaway numbers must not be presented as physical fusing temperatures.
- Engineering judgment for the requested rough estimate: thirty coils can plausibly reach about 100°C, with a broad approximate 80–160°C range under nominal 35 µm copper, room temperature, normal 200 ms / ~1 Hz pulses. This is a sensitivity envelope, not a guaranteed bound. Twenty-something coils are a lower-load validation region; thirty is a borderline test candidate. No established lifetime/current rating or sharp 36-coil damage / 50-coil fuse threshold follows. Fifty coils have much higher thermal risk (~2.75 times thirty-coil cold ON-time loss). Continuous-on/hold use is a different, more severe condition.
- Nearby plane copper spreads heat but does not electrically bypass the SW trace. Do not reduce local peak temperature to 20% merely because average duty is 20%; the short trace can heat substantially within 200 ms. Screen increasing dummy-load current while observing local temperature; no physical measurement has yet been received.
- Material references: [TI SNOA967A](https://www.ti.com/lit/an/snoa967a/snoa967a.pdf), [TI SNIA021](https://www.ti.com/lit/an/snia021/snia021.pdf). These support material conductivity / heat-flow considerations, not this board's estimated temperatures or coil-count limit.

### GPIO9 / OE compatibility

- U54 channel 2 connects 595 OE# to an intermediate node; channel 3 connects that node to GND. SEL2 is GPIO9; SEL3 is EN_MAIN. R11 pulls OE# up to VCC_LOGIC.
- With 3.3 V present and EN_MAIN high: **GPIO9 LOW disables outputs; GPIO9 HIGH enables outputs**. EN_MAIN low disables the series path.
- Current [V2.8 firmware](C:/Users/Hsinlung/Desktop/LingTouchCompanion/firmware/braille_15module_prod/braille_15module_prod.ino) sets GPIO9 HIGH in `initGPIO()`, then LOW in `sendRaw()` and at the end of setup. This is opposite to the new hardware's enable polarity. The initial HIGH can enable outputs before the first all-zero latch; actual startup behavior has not been measured.
- A compatible startup must keep output disabled while clearing the shift registers and latching zeros, then enable deliberately. SRCLR clears the shift register, not the output storage register. Firmware adaptation remains pending; no file was edited.
- `refreshGrouped()` enables SMA bit6 for every module in the batch, even if that module's requested coil data is zero. Default batch size is fifteen. `set N XX` therefore does not mean only N is electrically active.
- `moduleMask` is used by status printing and demo selection, but not by `refreshGrouped()`, ordinary `set`/`test`, raw frame processing or BLE refresh. It is not a functioning load-isolation control.
- `cmdHold()` blocks serial processing in second-long delays; `cmdEx()` blocks for its 400/300/600 ms cycles. The serial `stop` command cannot immediately interrupt these functions. Neither existing diagnostic is an appropriate first pulse test.
- Controlled bring-up needs correct OE polarity, disabled startup until zero is latched, actual coil-only/SMA-only/combined short-pulse selection, true module selection and a bounded pulse timeout. This analysis has not implemented those changes. External PSU output OFF remains the physical stop control during bench tests.
- Current firmware does not read PGOOD/GPIO14 or enable/sample the switched battery ADC through GPIO5/GPIO4. Hardware SMA gating still follows PGOOD; these features are not implemented software monitoring.
- The chain is U1 → … → U15 → U46. Groups 1–15 are U1–U15 → U16–U30 → U31–U45; group 16 is U46 → U47 → U48. The existing 15-byte reverse mapping addresses the first 15 groups correctly, but the 16th stage receives prior shifted data on later transfers. Keep U48 uninstalled until explicitly handled.

### Other observations

- U55 nominal startup is about **6.55 V** and falling shutdown about **5.74 V**, including R36 feedback. Do not describe this network as a verified 6 V cutoff or substitute for the external 2S protection board.
- Overlaying the official YD V1.4 dimensions places the antenna over the baseboard. GND/VCC planes occupy most of that projected region. BLE range remains unverified; this does not block no-load rail measurements.
- HC595 is powered at approximately 3.3 V. A 4.5 V per-pin test condition is not a complete 3.3 V loaded-VOH guarantee, nor a whole-chip current limit. Mixic ULN2003A has roughly 1 V saturation drop around 200 mA under the datasheet's drive conditions; actual module current and voltage need measurement.
- U50 RT6253A is a nominal 3 A converter shared by all fifteen SMAs. Hsinlung reports supplier SMA figures of approximately 0.08 A, maximum approximately 0.10 A each, giving 1.2–1.5 A total for fifteen. Rated-current mismatch is therefore not the present primary obstacle. Still check far-position voltage, driver loss, transient behavior and actual mechanical action. The 0.17 A coil budget is separate.
- ULN voltage loss applies to SMA as well as coils. A 3.53 V supply is not 3.53 V across a coil; a 2.00 V supply is not 2.00 V across the SMA. Measure each load between its own positive and switched return terminals. Test successful rise, reset/lock and holding after power is removed, not only a click or movement.
- Each ULN handles six coils plus an SMA, so package dissipation and repeated-pulse heat matter even when every channel is below its individual maximum. Six 0.17 A coils alone give roughly 1 W instantaneous ULN conduction loss if saturation is around 1 V; the intended 200 ms / 1 Hz pattern reduces time average but does not establish temperature.
- U52 is a 1.5 A maximum-continuous-current device on the ESP 5 V path, not a fifteen-module load path. YD's CJ6107 LDO also requires thermal verification; its 1 A typical headline is not a board-level continuous capability. At 0.30 A, an ideal 5-to-3.3 V drop alone dissipates about 0.51 W.
- The charging circuit disables battery-temperature sensing with R22 = 51k. BATM/BAT_GND are not connected for IP2326 cell balancing. The external 2S protection/balancing board must therefore be checked independently; charging to 8.3 V pack voltage does not alone establish safe individual-cell voltages.

## Assembly references and accessible measurement points

- **J3 = BAT+**, **J4 = GND**; both are backside circular solder pads, approximately 4 mm diameter. Main current must not use a single J_test pin.
- SW2: pin 1 GND, pin 2 switched control supply, pin 3 VBAT. Contacts 1–2 mean OFF; 2–3 mean ON. It switches control signals, so battery-input circuitry stays energized in OFF. SW1 is the separate optional button.
- ESP sockets: two 1 × 22, 2.54 mm pitch, 25.4 mm row spacing. USB end faces SW2/baseboard USB; antenna end faces the module area. Verify actual socket height and underside clearance before completing soldering.
- Tactile-module holes: two columns of six, 1.25 mm pitch, 4.96 mm column separation and 0.60 mm stagger. A standard 2.54 mm or aligned 2 × 6 header does not fit.
- C74–C79 pin 1 is VCC positive, pin 2 GND. C80 pin 1 is VBAT positive, pin 2 GND. D1/D2 pin 1 is cathode/GND. Backside viewing mirrors the top projection.
- [Measurement map](PCB_MEASURE_MAP_2026-10-07.png): viewed from TOP; J3/J4 are shown through the board. J_test's rightmost square pad is pin 1; numbers increase leftward.

| J_test | Net | J_test | Net |
| --- | --- | --- | --- |
| 1 | VCC | 12 | GND |
| 2 | GND | 13 | U1.SER |
| 3 | VCCS | 14 | GPIO13 |
| 4 | GND | 15 | GPIO4 / battery ADC |
| 5 | VCC_LOGIC | 16 | RCLK |
| 6 | ESP_3V3, before R19 | 17 | EN_MAIN |
| 7 | VBAT, after Q1 | 18 | 595 OE# |
| 8 | VIN_C, baseboard USB | 19 | GPIO9 / U54 SEL2 |
| 9 | GND | 20 | SRCLR# |
| 10 | V5S | 21 | U49 PGOOD |
| 11 | SRCLK | 22 | GND |

ESP `J_ESP_L`: pins 1/2 = 3.3 V, 12 = GPIO8/SRCLR, 15 = GPIO9/OE control, 16 = GPIO10/RCLK, 17 = GPIO11/SER, 18 = GPIO12/SRCLK, 20 = GPIO14/PGOOD, 21 = V5S, 22 = GND. `J_ESP_R` pin 1 = GND.

Each group: bit0–5 uses HC595 pins 15/1/2/3/4/5 → ULN inputs 1–6 → module pins 2/4/6/8/9/11. Bit6 uses HC595 pin 6 → ULN input 7 → module pin 3, SMA return. Bit7 unused. Module pins 1/5/7/10 = VCC; pin 12 = VCCS. ULN pin 8 = GND, pin 9 COM = VCC.

## Proposed bring-up sequence — no physical results yet

1. Verify solder bridges, fitted-part orientation, polarized parts and persistent near-zero rail-to-ground resistance. A changing resistance or brief continuity beep from charging capacitors is not alone evidence of a hard short.
2. With PSU output OFF, set 7.4 V / 0.10 A and SW2 OFF; connect J3 positive/J4 negative, then enable the supply. Check battery entry and EN_MAIN.
3. Switch PSU output OFF, set 0.30 A and SW2 ON, then enable again. Record steady input current and the rails below. Brief current limiting may be capacitive startup; sustained limiting or supply collapse is unresolved, not proof of a failed chip. Stop for sustained limiting, rapid heating or odor; do not blindly increase the limit.
4. After no-load VCC/V5S checks, power down and insert ESP, still without modules. A proposed 0.50 A input limit allows checking ESP startup, 3.3 V and VCCS. These PSU settings are test limits, not PCB current ratings.
5. Resolve OE startup compatibility before connecting one module. Verify one coil's short pulse, then SMA behavior and voltage drop/temperature. Existing `hold` defaults to 5 s and `ex` uses a 400 ms SMA window; neither is the initial validation command. Full simultaneous loading and charging need separate assessment.

Test objectives after no-load startup:
- A single-group test validates GPIO/OE, shift ordering, ULN outputs and real coil/SMA behavior; it does not prove fifteen-group power delivery.
- Increase coil load in stages using the intended 200 ms / approximately 1 Hz pulse sequence. Observe input collapse, VCC sag at near and far module supply holes, resets and repeated-pulse temperature rise. Add SMA overlap only after coil behavior is established. Do not substitute a prolonged all-on command for the intended duty cycle.
- The 15.3 A coil budget is regulator-output current, not bench-supply input current. Bench display and an ordinary multimeter may miss 200 ms transients; record this measurement limitation rather than claiming full-load validation from a normal average reading.
- Accessible DC comparison points include J3 versus C80 positive for battery-entry delivery and L1 VCC output versus C74 positive for VCC plane entry. Do not ask for live probing of U49's narrow SW pad; a meter reading there would not characterize the switching waveform anyway.
- USB charging is tested separately with a suitable protected 2S battery after basic power behavior is established. Do not connect charging USB while a conventional non-sinking PSU substitutes for the battery.

Nominal load estimates for sizing the test source, not measured or approved limits:
- Six coils per module: 1.02 A on VCC, fifteen modules: 15.3 A, approximately 54 W while energized at 3.53 V.
- Assuming 90% conversion efficiency at 7.4 V, fifteen coils groups alone require about 8.1 A at the battery input; around 5.74 V this becomes about 10.5 A. Add ESP, SMA and other losses. A lower-current bench supply cannot prove fifteen-group capability; its own current limiting must be distinguished from PCB failure.
- At 200 ms every second, ideal coil-rail average power is about 10.8 W. Do not use this average to judge startup, peak current, droop or transient heating.

Practical localization with common ground reference J4 and the same repeated test pattern:
| Observed behavior | Interpretation to investigate |
| --- | --- |
| PSU terminal voltage falls / current limit is reached | Source limit or test leads; not yet evidence of PCB failure |
| J3 remains stable but C80 positive/VBAT falls | Battery-entry/Q1/interconnect delivery path |
| VBAT remains stable but L1 VCC output falls | U49 conversion/input/return path, current limiting or transient response |
| L1 VCC output is stable but C74 positive falls | VCC-plane access path |
| C74 and near module VCC are stable, far module VCC falls | Distribution/connector delivery to the far position |
| Near 2 V falls with VBAT stable | U50 conversion capacity or transient response |
| Near 2 V is stable but far module pin12 falls | VCCS distribution or connector delivery |
| V5S stays stable but ESP 3.3 V falls/resets | Development-board input/LDO/3.3 V load path |
| Supplies are stable but bits or movements are wrong | OE/clock/cascade/mapping, driver voltage loss or module mechanics; isolate these next |

For functional testing, establish one coil and one SMA separately, then a whole six-coil group and the normal combined sequence. Compare near and far positions using a removable known module. Before a full real-module array, screen the power paths with dummy loads at increasing measured currents using the intended 200 ms / approximately 1 Hz pulse sequence. A continuous 15 A test is a different stress condition and cannot replace the intended-duty test.

Dummy-load boundaries:
- At 3.53 V, a nominal fifteen-group coil budget of 15.3 A corresponds to approximately 0.231 ohm and 54 W during ON time. These are sizing calculations, not a recommendation to immediately attach that resistance.
- A resistor alone is a static load. Controlled 200 ms pulses need an external timed load switch or a suitable dynamic electronic load; do not pretend manual contact or repeated PSU soft-start is an equivalent load transient.
- A central load at L1 output tests the converter, SW trace and inductor, but bypasses the VCC-plane entry/distribution paths. Distributed loads at actual supply positions can cover those paths; allocate current across the actual intended pins. Do not run fifteen amperes through one J_test or module pin or impose that current on a single capacitor-pad stub.
- Dummy load connected directly to supply/GND does not validate ULN output loss/heat, load inductance, flyback, SMA mechanics or the real connectors unless those paths are explicitly included.
- B passing does not prove A's solder quality or individual reliability. A also needs power-path screening, followed by real-array verification. Modules connected through sockets are removable; board failure does not inherently trap them, although a supply fault can damage attached modules.
- No dummy-load hardware has been selected, built or tested. Bench PSU capability, controlled pulse generation and suitable local temperature measurement remain unresolved equipment constraints for the full-current screen.

After power-path and real-array verification, finish with reduced battery voltage and the external protection board, then separate charging and finally the intended charging-plus-use condition.

| Point | SW2 OFF, no ESP | SW2 ON, no ESP | ON with ESP, no modules |
| --- | --- | --- | --- |
| J_test 7 VBAT | ~7.4 V | ~7.4 V | ~7.4 V |
| J_test 17 EN_MAIN | ~0 V | ~2.43 V | ~2.43 V |
| J_test 1 VCC | ~0 V after discharge | ~3.53 V | ~3.53 V |
| J_test 10 V5S | ~0 V after discharge | ~5 V | ~5 V |
| J_test 5/6 logic/raw 3.3 V | ~0 V | ~0 V | ~3.3 V |
| J_test 3 VCCS | ~0 V | ~0 V | ~2 V when PGOOD high |
| J_test 21 PGOOD | ~0 V | Usually ~0 V; pull-up unpowered | ~3.3 V when VCC good |

Without ESP, absent VCC_LOGIC/VCCS and an unlit D2 are expected. U54 is powered from ESP's 3.3 V; channel 4 passes PGOOD to EN_SMA only when EN_MAIN is high. D1 is a charging indicator. Keep USB cables disconnected while a normal bench PSU substitutes for the battery: the charger can drive current into BAT+, and the PSU is not known to sink current. USB-OTG and IN-OUT bypasses on the YD board are distinct; do not infer their states from each other.

SW2 OFF stops the enabled converters; it does not disconnect BAT+ from the board. Previously charged VCC/V5S capacitors may retain voltage, especially with no ESP or modules, so nonzero output voltage immediately after switching OFF is not by itself an enable fault. Check EN_MAIN and decay rather than requiring instantaneous zero. Before resistance measurements, confirm supply removal and discharged rails.

For undervoltage validation, start at 7.4 V and reduce the input slowly, recording EN_MAIN/PGOOD shutdown near the nominal 5.74 V falling threshold. Then raise it and record restart near 6.55 V. A fresh startup at 6.0 V is not expected with these thresholds; low-voltage load testing at 6.0 V must be reached by lowering an already-running supply. Use no modules for the first threshold sweep.

## Current electrical settings

| Circuit | Verified file settings / interpretation |
| --- | --- |
| U49 | MP8795HGLE-Z despite borrowed MPQ footprint name; L1 = 1 µH YSPI1365-1R0M; R7/R8 = 82.5k/16.9k, nominal 3.529 V; MODE R38 = 30.1k, about 800 kHz; R1 = 6.65k. Nominal valley OCP ~18 A, not a peak limit or protection for the thin traces. Ideal ripple at 7.4 V ~2.31 A. |
| U50 | RT6253AHGJ6F TSOT, 0.765 V reference; R9/R10 = 16.2k/10k, nominal 2.004 V; L2 = 2.2 µH. |
| U51/U52 | TPS630701 fixed 5 V, L3 = 1 µH; LM66100 reverse blocking, CE tied to V5S is intentional. |
| U55 | R34/R35/R36 = 150k/10k/390k; R6/R3 = 20k/10k; nominal comparator rising/falling thresholds 400/394.5 mV. |
| U53 | IP2326, R20 = 90k → nominal 1 A battery charge; R39 = 120k → ~8.3 V full charge; R21 = 120k → ~12 h timeout; R22 = 51k disables NTC; L4 = 2.2 µH. R23 = 0.5 Ω/0603 is only IC VIN filtering; L4 input directly uses VIN_C. Charging 2S at 1 A can draw about 2 A or more from 5 V, so charger-path capacity remains unresolved. |
| Local bypass | U49 C59/C60/C91; U50 C61/C62; U51 C63/C36. C71 = 1 µF on U49 internal VCC; C82 = 100 nF on U51 VAUX. |
| Bulk caps | Six 6SVPC330M, 330 µF/6.3 V, on VCC; C80 = 100 µF/16 V on VBAT. Nominal capacitance does not establish effective MLCC capacitance under DC bias. |
| Other interfaces | Q1 source = VBAT, drain = BAT+, intentional PMOS reverse-polarity topology. USB CC pull-downs R16/R17 = 5.1k. ADC divider R30/R15 = 100k/39k gives ~2.36 V at 8.4 V; U54 channel 1 controlled by GPIO5, default pulled low. |

## Manufacturer references used in the audit

- [MPS MP8795H](https://www.monolithicpower.com/en/documentview/productdocument/index/version/2/document_type/Datasheet/lang/en/sku/MP8795HGLE-Z/)
- [Richtek RT6253A/B](https://www.richtek.com/assets/product_file/RT6253A=RT6253B/DS6253AB-04.pdf)
- [TI TPS63070/701](https://www.ti.com/lit/ds/symlink/tps63070.pdf), [LM66100](https://www.ti.com/lit/ds/symlink/lm66100.pdf), [TMUX1511](https://www.ti.com/lit/ds/symlink/tmux1511.pdf), [TPS3700](https://www.ti.com/lit/ds/symlink/tps3700.pdf), [SN74HC595](https://www.ti.com/lit/ds/symlink/sn74hc595.pdf)
- [Injoinic IP2326, manufacturer-authored, M5Stack-hosted](https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/1132/IP2326.pdf)
- [Mixic ULN2003A, manufacturer-authored, LCSC-hosted](https://datasheet.lcsc.com/datasheet/pdf/54105fc0587bc762a1d5c58f9f51fcdc.pdf?productCode=C181730)
- [YJYCOIN YSPI1365, manufacturer-authored, LCSC-hosted](https://atta.szlcsc.com/upload/public/pdf/source/20221123/B5C8ED80AB877E8B7DB1203AF510D731.pdf)
- [TDK SPM5030VT](https://product.tdk.com/system/files/dam/doc/product/inductor/inductor/smd/catalog/inductor_automotive_power_spm5030vt-d_en.pdf)
- [YD-ESP32-S3 official hardware files](https://github.com/vcc-gnd/YD-ESP32-S3/tree/main/5-public-YD-ESP32-S3-Hardware%20info)
- [Espressif antenna/baseboard guidance](https://docs.espressif.com/projects/esp-hardware-design-guidelines/zh_CN/latest/esp32s3/pcb-layout-design.html)
