# Input provenance

- `BTTF_Glasses.3mf`: unchanged user-supplied BTTF Glasses archive. The Normal
  object is build object 2. `history/Headset_Prop_Stage1_2026-10-02/inspect_reference.py`
  reads its actual build axis scales, removes bed placement, and centers it.
  Wearing translation is `[0, 73.53516495, 27.587837475]` mm.
- `CS30_official.stp`: the previously downloaded official CS30 reference from
  the project reference collection. The current review's `inputs/CS30_customer.stp`
  is a different official STEP supplied for optical measurements; both are
  preserved. Do not substitute one for the other. The enclosure uses the
  user-specified finished-camera envelope 89.94 × 30 × 25 mm, rather than the
  internal STEP assembly's overall bounds.
- `Medium_Symmetry.stl`: actual NIOSH ISO Medium Symmetry headform, native mm,
  extracted from RD-10130-2020-0. The earlier local copy was removed; the same
  dataset was retrieved from `https://data.restoredcdc.org/rd/rd-10130-2020-0.zip`.
  The registration generated from this STL was verified vertex-for-vertex and
  face-for-face against the existing `Medium_Trial_Registered.npz`.
  `MaterialsMethodsISODigitalHeadforms.pdf` comes from that archive.
- Battery envelope source: Hsinlung's original instruction: “充电宝换成
  NITECORE Carbon Battery 6K：圆柱，直径 22.8，长 90.4，重 88g。”
  Thus the actual envelope is a cylinder Ø22.8 × 90.4 mm, axis X.
  These are supplied dimensions, not measurements made by these scripts.
  The earlier 117 × 47 × 15 mm block belongs to a superseded design.

## Head registration

Scale is exactly 1, with no deformation. Column-vector native-to-wearing matrix:

```
[[1, 0,  0,   0.00000000000000005551115123125783],
 [0, 0, -1, 105.16174806522717],
 [0, 1,  0,  14.958561080000006],
 [0, 0,  0,   1]]
```

The original `register_head.py` reproduces the datum selection. This is the
existing trial pose, not a claim that the original arms fit this unscaled head.
The full registration record is produced under `.build/headset_<part>/`.
