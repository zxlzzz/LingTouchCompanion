"""Verify actual added-case NPZ. Input must exclude original BTTF mesh.

Usage: python verify_actual_case_distance.py path/to/added_case.npz
Accepted vertex keys: v or vertices; face keys: f or faces.
"""
from pathlib import Path
import sys,json,hashlib,numpy as np
from triangle_distance import min_triangle_distance,clip_triangles_y_negative
P=Path(__file__).resolve().parent
source=Path(sys.argv[1]).resolve();q=np.load(source)
v=q['v'] if 'v' in q else q['vertices'];f=q['f'] if 'f' in q else q['faces']
C,case_source_ids=clip_triangles_y_negative(v,f,limit=-1e-6)
h=np.load(P/'Medium_Trial_Registered.npz');hv,hf=h['v'],h['f'];tri=hv[hf]
nasal=(np.abs(tri[:,:,0]).max(1)<30)&(tri[:,:,1].min(1)<12)&(tri[:,:,2].max(1)>-10)&(tri[:,:,2].min(1)<45)
head_ids=np.flatnonzero(nasal);H=tri[nasal]
answer=min_triangle_distance(H,C)
report={'case_source':str(source),'scope':'Actual newly added case triangles clipped to Y<0. Original BTTF surfaces excluded by input contract. Y0 edge is valid limit of nearby Y<0 surfaces; faces lying whollyY0 are excluded.',
 'case_source_npz_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'case_source_vertices':len(v),'case_source_triangles':len(f),
 'head_source':str(P/'Medium_Trial_Registered.npz'),'unchanged_head_trial_pose':True,'full_original_BTTF_wearing_verified':False,
 'strict_y_case_limit_mm':-1e-6,'distance_mm':answer[0],'nose_witness_xyz_mm':answer[1].tolist(),'case_witness_xyz_mm':answer[2].tolist(),'head_original_triangle_index':int(head_ids[answer[3]]),'case_original_triangle_index':int(case_source_ids[answer[4]]),
 'head_triangles_tested':len(H),'case_triangles_after_y_clip':len(C),'nose_region_definition':'Original head triangles with allabsX<30, minimumY<12, maximumZ>-10, minimumZ<45. Includes nose, nasal root and nearby upper face; no synthetic nose.',
 'method':'Continuous triangle-triangle closest-feature test: all vertex-face, interior edge-edge, both directions of segment-face intersection. Uses original anatomical triangles.',
 'passes_2mm':answer[0]>=2}
(P/'actual_case_nose_distance.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
