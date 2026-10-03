# Original inputs and fixed datums

- BTTF_Glasses.3mf is the unchanged original archive. Normal is build object 2;
  build axis scales are read and bed placement is removed. Wearing translation
  is recorded in datums.json. It supplies the original volume comparison.
- CS30_customer.stp is Hsinlung's actual camera assembly, used for the body and
  three optical-port positions. CS30_official.stp is a separate original
  reference retained for provenance; it must not replace the customer STEP.
- Medium_Symmetry.stl is the original NIOSH ISO Medium Symmetry headform, native
  millimeters, from RD-10130-2020-0. The companion methods PDF is original.
  Dataset source: https://data.restoredcdc.org/rd/rd-10130-2020-0.zip
- datums.json preserves the scale-1 head registration and current terminal
  strap slots. prepare.py regenerates Medium_Trial_Registered.npz from the STL.
  No head deformation or scaling is used.

All models use X lateral, Y posterior, Z up. Rear battery dimensions were
provided by Hsinlung: cylinder diameter 22.8 mm, length 90.4 mm, mass 88 g.
Current front and rear generators reference these inputs directly.
