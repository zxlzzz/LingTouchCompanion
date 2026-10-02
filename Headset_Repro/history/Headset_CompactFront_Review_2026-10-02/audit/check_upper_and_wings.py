from pathlib import Path
import numpy as np, manifold3d as md, json, hashlib
P=Path(__file__).resolve().parent;G=P.parent/'geometry';M=md.Manifold
def load(path):
 a=np.load(path);return M(md.Mesh64(vert_properties=a['v'],tri_verts=a['f'].astype(np.uint64)))
def box(a,b):return M.cube(tuple(np.array(b)-a)).translate(tuple(a))
v=json.loads((G/'geometry_values.json').read_text());T=np.array(v['camera_transform']);front=load(G/'front_unified_preview.npz')
below=box([-100,-100,-100],[100,-2.500001,150]).transform(T.tolist())
wingvols={s:max(0,(load(G/('wing_'+s+'.npz'))^below).volume()) for s in ['left','right']}
# Compare outer boundary of original upper rim with the actual57.14 contact plane.
base=load(G/'original_modified.npz')+load(G/'front_tabs.npz')
original_top=base.slice(55.12);contact=front.slice(57.13999)
points=np.concatenate(original_top.to_polygons()); missing=[]
for q in points:
 local=md.CrossSection.square((.002,.002),center=True).translate(tuple(q))
 if (local^contact).area()<1e-9:missing.append(q.tolist())
result={'source_sha256':hashlib.sha256((G/'front_unified_preview.npz').read_bytes()).hexdigest(),'wing_new_material_below_camera_outer_bottom_plane_mm3':wingvols,'top_contact_plane_z_mm':57.14,'original_rim_boundary_points_tested':len(points),'original_rim_boundary_points_missing_at_top':len(missing),'missing_xy_examples':missing[:12],'interpretation':'Missing boundary points include the deliberately relieved face-side rim. This does not certify every old upper edge was raised; top-contact surfaces themselves are coplanar.'}
(P/'upper_and_wings.json').write_text(json.dumps(result,indent=2),encoding='utf8');print(json.dumps(result,indent=2))
