"""Review-only compact shell; immutable original inputs and explicit conflicts."""
from pathlib import Path
import math,json,hashlib
import numpy as np
import manifold3d as md
P=Path(__file__).resolve().parent;ROOT=P.parents[1]
OLD=ROOT/'Headset_CompactFront_Review_2026-10-02/inputs'
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
 poly=np.asarray(poly); area=np.sum(poly[:,0]*np.roll(poly[:,1],-1)-poly[:,1]*np.roll(poly[:,0],-1)); poly=poly if area>0 else poly[::-1]; cs=md.CrossSection([poly]);m=cs.extrude(xhi-xlo)
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
 for n,d in [(frontn,np.dot(frontn,pivot)+(27 if outer else 25.000001)),(-floorn,-np.dot(floorn,pivot)+(2.5 if outer else .5)),([0,1],TOPOUT if outer else TOPIN),(N,np.dot(N,pivot)+R+(.3+2 if outer else .3))]:p=clip(p,np.array(n),d)
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
ucuts=[];hooks=[];springs=[];flex_sweeps=[]
def flex_section(x,t0,t1,delta,hook=False):
 def sag(t):
  q=np.clip((13-t)/14,0,1);return delta*q*q*(3-q)/2
 hs=[(-1,-1.5),(-.1,-1.5),(-.1,.8),(-1,.8)] if hook else [(t0,-1.5),(t1,-1.5),(t1,-.5),(t0,-.5)]
 yz=[(pivot+np.array([-C*t-S*(h-sag(t)),-S*t+C*(h-sag(t))])).tolist() for t,h in hs]
 return prism(yz,x-3,x+3)
for x in [-30,30]:
 u=union([box([x-3.6,-5,-1.6],[x-3,-.4,13]),box([x+3,-5,-1.6],[x+3.6,-.4,13]),box([x-3.6,-5,-1.6],[x+3.6,1,-1.0]),box([x-3,-5,-1],[x+3,-1.5,12.99])])
 ucuts.append(tf(u));hook=flex_section(x,0,0,0,True);hooks.append(hook)
 segments=[];swept=[]
 for t0,t1 in zip(np.linspace(-1,13,57)[:-1],np.linspace(-1,13,57)[1:]):
  a=flex_section(x,t0,t1,0);b=flex_section(x,t0,t1,1.4);segments.append(a)
  if t1<12.99:swept.append(M.batch_hull([a,b]))
 springs.append(union(segments));swept.append(M.batch_hull([hook,flex_section(x,0,0,1.4,True)]))
 flex_sweeps.append(union(swept))
ucuts=union(ucuts);hooks=union(hooks);springs=union(springs);flex_sweep=union(flex_sweeps)
shell=shell-ucuts+springs+hooks
registration_x=.029053624731608
optics=[{'name':'RGB','x':-22-registration_x,'h':15.,'diameter':9.95,'clear_glass_diameter':8.8,'front_t':23.87,'fov':[112,63]},
 {'name':'TX','x':7-registration_x,'h':15.005,'diameter':math.hypot(2.79,2.84),'front_t':23.3,'fov':[110,90],'rectangular_source_mm':[2.79,2.84]},
 {'name':'RX','x':22-registration_x,'h':15.,'diameter':10.5,'clear_glass_diameter':9.6,'front_t':23.442,'fov':[100,75]}]
def oval_section(x,h,rx,ry):
 a=np.linspace(0,2*math.pi,193)[:-1];q=1/math.cos(math.pi/192)
 return md.CrossSection([np.array([x+rx*q*np.cos(a),h+ry*q*np.sin(a)]).T])
def aperture(indices):
 radius=max(optics[i]['diameter']/2+.5 for i in indices)
 slope=[max(math.tan(math.radians(optics[i]['fov'][j]/2)) for i in indices) for j in [0,1]]
 def sec(t):
  sections=[oval_section(optics[i]['x'],optics[i]['h'],radius+max(0,t-25)*slope[0],radius+max(0,t-25)*slope[1]) for i in indices]
  return sections[0] if len(indices)==1 else md.CrossSection.batch_hull(sections)
 parts=[]
 for a,b in [(24.999,25),(25,27),(27,30)]:
  def plate(t):return sec(t).extrude(.000001).translate((0,0,t))
  parts.append(M.batch_hull([plate(a),plate(b)]))
 return tf(union(parts)),{'names':[optics[i]['name'] for i in indices],'merged':len(indices)>1,
  'inner_width_height_mm':[float(np.ptp(np.concatenate(sec(25).to_polygons())[:,j])) for j in [0,1]],
  'outer_width_height_mm':[float(np.ptp(np.concatenate(sec(27).to_polygons())[:,j])) for j in [0,1]],'max_side_slopes':slope}
pre_gap=15-(optics[1]['diameter']/2+.5+2*math.tan(math.radians(55)))-(5.25+.5+2*math.tan(math.radians(50)))
groups=[[0],[1,2]] if pre_gap<2 else [[0],[1],[2]]
apertures=[aperture(a) for a in groups];window=union([a[0] for a in apertures]);shell-=window
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
original_modified-=box([-45.3,-50,24.34],[45.3,30,100])
original_modified-=flex_sweep
wings=[load(OLD/('wing_'+s+'.npz')) for s in ['left','right']]
centralbelow=tf(box([-47.3,-250,-250],[47.3,-2.5,250]))
# Region boundary0.03mm strip belongs to the camera region: no new low material.
wings=[w ^ abovefloor for w in wings]
front_half=prism(clip([[-120,-50],[150,-50],[150,100],[-120,100]],frontn,np.dot(frontn,pivot)+27),-100,100)
wings=[w^front_half for w in wings]
# Raise the existing thin wing roof rather than stacking solid rim material.
def raise_wing_roof(w):
 lower=w ^ box([-100,-150,-10],[100,200,45.0])
 upper=w ^ box([-100,-150,45.0],[100,200,80])
 connector=w.slice(44.99999).extrude(1.94002).translate((0,0,44.99999))
 return union([lower,upper.translate((0,0,1.94)),connector])
wings=[raise_wing_roof(w) for w in wings]
tabs=load(OLD/'front_tabs.npz')
base_top=union([original_modified,tabs])
rim=base_top.slice(55.12).extrude(57.14-55.12).translate((0,0,55.12))
head_data=np.load(ROOT/'Headset_Carbon6K_FlatBase_Review_2026-10-02/inputs/Medium_Trial_Registered.npz')
head_tri=head_data['v'][head_data['f']]
def enclosing_ball(radius):
 ball=M.sphere(1,circular_segments=32);a=ball.to_mesh64();v=np.array(a.vert_properties)[:,:3];f=np.array(a.tri_verts);tri=v[f]
 n=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]);d=np.abs(np.sum(n*tri[:,0],axis=1))/np.linalg.norm(n,axis=1)
 q=radius/float(d.min()); return ball.scale((q,q,q))
nasal_keep=(np.abs(head_tri[:,:,0]).max(1)<30)&(head_tri[:,:,1].min(1)<12)&(head_tri[:,:,2].max(1)>-10)&(head_tri[:,:,2].min(1)<45)
nose_guard=M.hull_points(head_tri[nasal_keep].reshape(-1,3)).minkowski_sum(enclosing_ball(2.01))
nose_removed=shell^nose_guard;shell-=nose_guard
cap_keep=(head_tri[:,:,2].max(1)>54.8)&(head_tri[:,:,2].min(1)<57.5)
cap_guard=M.hull_points(head_tri[cap_keep].reshape(-1,3)).minkowski_sum(enclosing_ball(.08))

base_top=union([original_modified,tabs])
rim=base_top.slice(55.12).extrude(57.14-55.12).translate((0,0,55.12))
rim_removed=rim ^ cap_guard; rim-=cap_guard
new=union([shell,*wings,rim])
front=union([original_modified,new,tabs])
parts=front.decompose();positive=[p for p in parts if p.volume()>1e-5];negative=[p for p in parts if p.volume()<-1e-5]
assert len(positive)==1,[(p.volume(),p.bounding_box()) for p in parts]
front=union([*positive,*negative])
report={'inspection_only':True,'pivot_yz_mm':[PY,PZ],'rounded_requested_pivot_yz_mm':[2.6,24.84],'exact_old_floor_plane_preserved':True,'camera_transform':T.tolist(),'top_inner_outer_z_mm':[TOPIN,TOPOUT],'chamfer_inner_outward_normal_yz':N.tolist(),'chamfer_arc_clearance_analytic_mm':.3,'chamfer_normal_wall_mm':2,'profiles_yz_mm':{'outer':outerp,'inner':innerp},'source_hashes':{n:hashlib.sha256((OLD/n).read_bytes()).hexdigest() for n in ['original_reference.npz','front_tabs.npz','wing_left.npz','wing_right.npz']},'geometry':{}}
for name,m in [('original',original),('original_modified',original_modified),('camera',camera),('camera_flat',box([-44.97,PY-25,PZ],[44.97,PY,PZ+30])),('central_shell',shell),('new_shell',new),('front_tabs',tabs),('tabs_added',tabs-original),('front_unified_preview',front),('added_material',union([new,tabs])-original),('hooks',hooks),('ucuts',ucuts),('entry_sweep',entry),('rotation_sweep',rotation),('window_cut',window),('central_envelope',outer^mask),('wing_left',wings[0]),('wing_right',wings[1])]:report['geometry'][name]=save(name,m)
for x in [0,30]:
 for source,name in [(original_modified,'original'),(new,'shell'),(camera,'camera')]:save('section'+str(x)+'_'+name,source^box([x,-250,-50],[200,350,150]))
report['volume_cm3']=front.volume()/1000
report['optics']=optics
report['optical_apertures']=[a[1] for a in apertures]
report['unmerged_TX_RX_outer_material_gap_mm']=pre_gap
report['spring']={'centers_x_mm':[-30,30],'length_mm':14,'width_mm':6,'thickness_mm':1,'hook_top_over_camera_bottom_plane_mm':.8,'hook_rear_optical_t_range_mm':[-1,-.1],'hook_front_gap_mm':.1,'verified_normal_travel_mm':1.4,'strain_formula_value':3*1*1.4/(2*14**2),'hook_joint_cross_section_mm2':6,'spring_cross_section_mm2':6}
report['flat_cut_z_mm']=24.34
report['top_rim_volume_cm3']=rim.volume()/1000
report['additional_clearance_reliefs_cm3']={'face_side_floor_for_2mm_nose_clearance':nose_removed.volume()/1000,'raised_rim_for_head_clearance':rim_removed.volume()/1000}
save('nose_clearance_guard',nose_guard);save('rim_head_clearance_guard',cap_guard)
save('spring_bodies',springs);save('spring_deflection_sweep',flex_sweep);save('top_rim',rim)
save('front_without_springs',front-(springs+hooks));save('front_without_hooks',front-hooks)
for x in [-30,30]:save('spring_deflected_'+str(x),union([flex_section(x,t0,t1,1.4) for t0,t1 in zip(np.linspace(-1,13,57)[:-1],np.linspace(-1,13,57)[1:])])+flex_section(x,0,0,1.4,True))
# Rectangular angular pyramids are conservative for the full H/V field.
cones=[]
for o in optics:
 points=[[o['x'],o['h'],o['front_t']]]
 for xx in [-1,1]:
  for hh in [-1,1]:points.append([o['x']+xx*(27-o['front_t'])*math.tan(math.radians(o['fov'][0]/2)),o['h']+hh*(27-o['front_t'])*math.tan(math.radians(o['fov'][1]/2)),27])
 cone=tf(M.hull_points(points));cones.append(cone)
report['optical_cone_shell_intersection_mm3']=float((union(cones)^front).volume())
save('optical_field_pyramids',union(cones))
report['camera_exact_corners_yz_mm']={n:(pivot+np.array([-C*t-S*h,-S*t+C*h])).tolist() for n,t,h in [('rear_lower',0,0),('front_lower',25,0),('front_upper',25,30),('rear_upper',0,30)]}
report['removed_old_wing_boundary_strip_mm3']=[(load(OLD/('wing_'+s+'.npz'))-w).volume() for s,w in zip(['left','right'],wings)]
report['below_floor_added_camera_region_mm3']=(new^centralbelow).volume()
(P/'geometry_values.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps({'volume_cm3':report['volume_cm3'],'front':report['geometry']['front_unified_preview'],'central':report['geometry']['central_shell'],'wing_strip_removed_mm3':report['removed_old_wing_boundary_strip_mm3']},indent=2))










