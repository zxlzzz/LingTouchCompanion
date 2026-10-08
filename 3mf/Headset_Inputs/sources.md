# Required model inputs

- Front_CS30_Mount_Final.3mf is Hsinlung's actually printed front, supplied
  on 2026-10-06. SHA256:
  ef1406f50a50c62fd6e395560f89924b7d319fddc9b5e95bdd94fbafb40aea61.
  It contains the finished geometry, baked print pose and printing settings.
- Medium_Symmetry.stl is the unchanged scale-1 NIOSH ISO Medium Symmetry
  headform from RD-10130-2020-0. Dataset source:
  https://data.restoredcdc.org/rd/rd-10130-2020-0.zip
  prepare.py and datums.json regenerate its registered rear reference mesh.
- ../Headset_Rear/inputs/rear_tray.npz and rear_fill.npz preserve the anatomical
  tray and outer connector surface required by the final rear construction.
  Their provenance and expected generated array hashes are retained in
  ../Headset_Rear/source_provenance.json.

The rear/reference axes are X lateral, Y posterior, Z up. The front retains
its own print coordinates; current camera/head registration is not inferred.
