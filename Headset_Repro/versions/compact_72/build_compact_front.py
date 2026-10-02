"""Review-only compact shell; immutable original inputs and explicit conflicts."""
from pathlib import Path
import math,json,hashlib
import numpy as np
import manifold3d as md
P=Path(__file__).resolve().parent;ROOT=P.parents[1]
OLD=ROOT/'Headset_ThinShell_Review_2026-10-02/geometry'
M=md.Manifold;C=math.cos(math.radians(20));S=math.sin(math.radians(20))
# Preserve the exact old bottom plane by translating along the optical axis.
PY=-.8+C*3.62;PZ=23.6+S*3.62
T=np.array([[1,0,0,0],[0,-S,-C,PY],[0,C,-S,PZ]],float)
def box(lo,hi):
 lo=np.array(lo,float);hi=np.array(hi,float);return M.cube(tuple(hi-lo)).translate(tuple(lo))
def tf(m):return m.transform(T)
def load(path):
 a=np.load(path);return M(md.Mesh64(vert_properties=np.ascontiguousarray(a['v'],dtype=np.float64),tri_verts=np.ascontiguousarray(a['f'],dtype=np.uint64)))
def save(name,m):
 assert m.status()==md.Error.NoError,(name,m.status())
 a=m.to_mesh64();v=np.array(a.vert_properties)[:,:3];f=np.array(a.tri_verts)
 np.savez_compressed(P/(name+'.npz'),v=v,f=f)
 return {'volume_mm3':float(m.volume()),'bounds_xyz_mm':[v.min(0).tolist(),v.max(0).tolist()] if len(v) else None,'triangles':len(f),'components':len(m.decompose())}
def union(ms):return M.batch_boolean(ms,md.OpType.Add)
def prism(poly,xlo,xhi):
 cs=md.CrossSection([poly]);m=cs.extrude(xhi-xlo)
 # local section u=Y,v=Z; extrusion w=X.
 return m.transform([[0,0,1,xlo],[1,0,0,0],[0,1,0,0]])
def clip(poly,n,d):
 out=[]
 for a,b in zip(poly,poly[1:]+poly[:1]):
  a=np.array(a);b=np.array(b);da=np.dot(n,a)-d;db=np.dot(n,b)-d
  if da<=1e-12:out.append(a.tolist())
  if (da<0)!=(db<0):out.append((a+(b-a)*da/(da-db)).tolist())
 return out
R=math.hypot(25,30);N=np.array([-25*C-30*S,-25*S+30*C])/R
pivot=np.array([PY,PZ]);frontn=np.array([-C,-S]);floorn=np.array([-S,C])
TOPIN=55.14;TOPOUT=57.14
def profile(outer):
 p=[[-100,-20],[100,-20],[100,100],[-100,100]]
 for n,d in [(frontn,np.dot(frontn,pivot)+(27 if outer else 25)),(-floorn,-np.dot(floorn,pivot)+(2.5 if outer else .5)),([0,1],TOPOUT if outer else TOPIN),(N,np.dot(N,pivot)+R+(.3+2 if outer else .3))]:p=clip(p,np.array(n),d)
 return p
outerp=profile(True);innerp=profile(False)
outer=prism(outerp,-47.27,47.27);inner=prism(innerp,-45.27,45.27)
limit=load(OLD/'actual_original_forward_limit.npz')
# Above the real original top, use the unchanged upper rear outline projected vertically.
limtop=limit.slice(55.17567495-.00001).extrude(10).translate((0,0,55.17567495-.00001))
mask=union([limit,box([-80,-120,0],[80,0,80]),limtop])
camera=tf(box([-44.97,0,0],[44.97,30,25]))
shell=(outer-inner)^mask
# Rear end of the floor stops at t=0; cantilevers point forward into the floor.
floorrear=tf(box([-50,-3,-150],[50,-.499999,0]))
shell-=floorrear
ucuts=[];hooks=[]
for x in [-30,30]:
 u=union([box([x-3.6,-3,0],[x-3,-.4,8]),box([x+3,-3,0],[x+3.6,-.4,8]),box([x-3.6,-3,-.01],[x+3.6,-.4,.6])])
 ucuts.append(tf(u));hooks.append(tf(box([x-3,-.52,-.8],[x+3,.3,.8])))
ucuts=union(ucuts);hooks=union(hooks);shell=shell-ucuts+hooks
# Reuse precisely the previous beveled stadium opening, translate with camera.
window=load(OLD/'window_cut.npz').translate((0,C*3.62,S*3.62));shell-=window
# Conservative continuous rotation envelope: convex hull of sampled corners,
# with circumscribed small offset covering chordal sagitta.
pts=[]
for theta in np.linspace(0,20,401):
 a=math.radians(theta);c,s=math.cos(a),math.sin(a)
 for h in [-.5,30.3]:
  for t in [0,25]:pts.append([PY-c*t-s*h,PZ-s*t+c*h])
cs=md.CrossSection.hull_points(np.array(pts)).offset(.00001)
rotation=cs.extrude(90.54).transform([[0,0,1,-45.27],[1,0,0,0],[0,1,0,0]])
horizontal=box([-45.27,PY-25,PZ-.5],[45.27,200,PZ+30.3])
entry=union([rotation,horizontal])
abovefloor=tf(box([-200,-2.5,-250],[200,200,250]))
original=load(OLD/'original_reference.npz')
# Preserve every original point below the outer bottom face, as requested.
original_modified=original-(entry^abovefloor)
wings=[load(OLD/('wing_'+s+'.npz')) for s in ['left','right']]
centralbelow=tf(box([-47.3,-250,-250],[47.3,-2.5,250]))
# Region boundary0.03mm strip belongs to the camera region: no new low material.
wings=[w-centralbelow for w in wings]
tabs=load(OLD/'front_tabs.npz')
new=union([shell,*wings])
front=union([original_modified,new,tabs])
parts=front.decompose();positive=[p for p in parts if p.volume()>1e-5];negative=[p for p in parts if p.volume()<-1e-5]
assert len(positive)==1,[(p.volume(),p.bounding_box()) for p in parts]
front=union([*positive,*negative])
report={'inspection_only':True,'pivot_yz_mm':[PY,PZ],'rounded_requested_pivot_yz_mm':[2.6,24.84],'exact_old_floor_plane_preserved':True,'camera_transform':T.tolist(),'top_inner_outer_z_mm':[TOPIN,TOPOUT],'chamfer_inner_outward_normal_yz':N.tolist(),'chamfer_arc_clearance_analytic_mm':.3,'chamfer_normal_wall_mm':2,'profiles_yz_mm':{'outer':outerp,'inner':innerp},'source_hashes':{n:hashlib.sha256((OLD/n).read_bytes()).hexdigest() for n in ['original_reference.npz','front_tabs.npz','wing_left.npz','wing_right.npz']},'geometry':{}}
for name,m in [('original',original),('original_modified',original_modified),('camera',camera),('camera_flat',box([-44.97,PY-25,PZ],[44.97,PY,PZ+30])),('central_shell',shell),('new_shell',new),('front_tabs',tabs),('front_unified_preview',front),('added_material',new-original),('hooks',hooks),('ucuts',ucuts),('entry_sweep',entry),('rotation_sweep',rotation),('window_cut',window),('central_envelope',outer^mask),('wing_left',wings[0]),('wing_right',wings[1])]:report['geometry'][name]=save(name,m)
for x in [0,30]:
 for source,name in [(original_modified,'original'),(new,'shell'),(camera,'camera')]:save('section'+str(x)+'_'+name,source^box([x,-250,-50],[200,350,150]))
report['volume_cm3']=front.volume()/1000
report['camera_exact_corners_yz_mm']={n:(pivot+np.array([-C*t-S*h,-S*t+C*h])).tolist() for n,t,h in [('rear_lower',0,0),('front_lower',25,0),('front_upper',25,30),('rear_upper',0,30)]}
report['removed_old_wing_boundary_strip_mm3']=[(load(OLD/('wing_'+s+'.npz'))-w).volume() for s,w in zip(['left','right'],wings)]
report['below_floor_added_camera_region_mm3']=(new^centralbelow).volume()
(P/'geometry_values.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps({'volume_cm3':report['volume_cm3'],'front':report['geometry']['front_unified_preview'],'central':report['geometry']['central_shell'],'wing_strip_removed_mm3':report['removed_old_wing_boundary_strip_mm3']},indent=2))
