from pathlib import Path
import json,numpy as np,manifold3d as md
P=Path(__file__).resolve().parent
w=json.loads((P/'surface_visibility_thickness_checks.json').read_text())['original_face_side_material_samples']['maximum_sample_xyz_mm']
x,y,z=w
a=np.load(P/'original_reference.npz');tri=a['v'][a['f']];aa,bb,cc=tri[:,0],tri[:,1],tri[:,2]
den=(bb[:,2]-cc[:,2])*(aa[:,0]-cc[:,0])+(cc[:,0]-bb[:,0])*(aa[:,2]-cc[:,2])
good=(abs(den)>1e-15)&(tri[:,:,0].min(1)<=x+1e-9)&(tri[:,:,0].max(1)>=x-1e-9)&(tri[:,:,2].min(1)<=z+1e-9)&(tri[:,:,2].max(1)>=z-1e-9)
aa,bb,cc=aa[good],bb[good],cc[good];d=den[good]
p=((bb[:,2]-cc[:,2])*(x-cc[:,0])+(cc[:,0]-bb[:,0])*(z-cc[:,2]))/d
q=((cc[:,2]-aa[:,2])*(x-cc[:,0])+(aa[:,0]-cc[:,0])*(z-cc[:,2]))/d
hit=(p>=-1e-8)&(q>=-1e-8)&(p+q<=1+1e-8)
ys=p[hit]*aa[hit,1]+q[hit]*bb[hit,1]+(1-p[hit]-q[hit])*cc[hit,1]
r={'witness':w,'exact_raw_triangle_intersections_y':ys.tolist(),'raw_triangle_y_overrun':y-float(max(ys))}
for name in ['original','actual_original_forward_limit','new_shell']:
 a=np.load(P/(name+'.npz'));m=md.Manifold(md.Mesh64(vert_properties=np.ascontiguousarray(a['v'],dtype=np.float64),tri_verts=np.ascontiguousarray(a['f'],dtype=np.uint64)))
 hits=m.ray_cast((x,-100,z),(x,60,z));r[name+'_ray_y']=[h.position[1] for h in hits]
(P/'overrun_witness_check.json').write_text(json.dumps(r,indent=2),encoding='utf8')
print(json.dumps(r,indent=2))
