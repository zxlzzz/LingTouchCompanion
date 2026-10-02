from pathlib import Path
import json
import numpy as np
P=Path(__file__).resolve().parent
a=np.load(P/'rear_inner_surface.npz');v=a['v'];f=a['f'];t=v[f]
points=[v[(v[:,0]>=-60.8)&(v[:,0]<=60.8)]]
for x in [-60.8,60.8]:
 for i,j in [(0,1),(1,2),(2,0)]:
  u,w=t[:,i],t[:,j];d=w[:,0]-u[:,0];ok=(abs(d)>1e-12)&((u[:,0]-x)*(w[:,0]-x)<=0)
  points.append(u[ok]+(w[ok]-u[ok])*(((x-u[ok,0])/d[ok])[:,None]))
points=np.concatenate(points);nearest=points[points[:,1].argmin()]
b=json.loads((P/'rear_assembly_values.json').read_text());back=np.array([nearest[0],b['rear_bounds_xyz_mm'][1][1],nearest[2]])
report={'method':'Continuous linear rear-inner triangles clipped to|X|<=60.8; local overallY envelope extends to the flat outer back faceY222.9. Includes battery cavity, not a solid-wall thickness.',
 'maximum_local_fore_aft_envelope_mm':float(back[1]-nearest[1]),'inner_front_witness_xyz_mm':nearest.tolist(),'outer_back_witness_xyz_mm':back.tolist(),
 'overall_y_bounding_span_mm':b['rear_y_bounding_span_mm'],'overall_width_mm':b['rear_width_mm'],
 'tray_minimum_wall_separately_measured_in':'rear_actual_clearance.json'}
(P/'rear_maximum_thickness.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report,indent=2))
