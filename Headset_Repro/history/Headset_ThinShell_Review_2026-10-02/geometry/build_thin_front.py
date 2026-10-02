"""Thin-shell inspection geometry only. No final printing file is exported.

Original BTTF vertices are preserved; only the specified camera-entry sweep
is subtracted. Fixed camera position, 2mm shell plates and existing ears.
Impossible specification combinations are recorded, not silently relaxed.
"""
from pathlib import Path
import hashlib,json,math
import numpy as np
import trimesh
import manifold3d as md

P=Path(__file__).resolve().parent
ROOT=P.parents[1]
SOURCE=ROOT/'Headset_FullCase_30mm_Preview_2026-10-02/preview_work/original_reference.npz'
M=md.Manifold;C=math.cos(math.radians(20));S=math.sin(math.radians(20));TAN=S/C
T=np.array([[1,0,0,0],[0,-S,-C,-.8],[0,C,-S,23.6],[0,0,0,1]],float)

def box(lo,hi):
 lo=np.asarray(lo,float);hi=np.asarray(hi,float)
 return M.cube(tuple(hi-lo)).translate(tuple(lo))
def tf(m):return m.transform(T[:3,:4])
def union(ms):return M.batch_boolean(ms,md.OpType.Add)
def mesh(v,f):
 a=trimesh.Trimesh(v,np.asarray(f),process=True);trimesh.repair.fix_normals(a,multibody=True)
 return M(md.Mesh64(vert_properties=np.ascontiguousarray(a.vertices,dtype=np.float64),tri_verts=np.ascontiguousarray(a.faces,dtype=np.uint64)))
def save(name,m):
 assert m.status()==md.Error.NoError,(name,m.status())
 a=m.to_mesh64();v=np.array(a.vert_properties)[:,:3];f=np.array(a.tri_verts)
 np.savez_compressed(P/(name+'.npz'),v=v,f=f)
 return {'vertices':len(v),'triangles':len(f),'bounds_xyz_mm':[v.min(0).tolist(),v.max(0).tolist()],'volume_mm3':float(m.volume()),'components':len(m.decompose()),'status':str(m.status())}

A=np.load(SOURCE);v=A['v'];f=A['f'];tri=v[f]
original=M(md.Mesh64(vert_properties=np.ascontiguousarray(v,dtype=np.float64),tri_verts=np.ascontiguousarray(f,dtype=np.uint64)))
np.savez_compressed(P/'original_reference.npz',v=v,f=f)
a,b,c=tri[:,0],tri[:,1],tri[:,2]
den=(b[:,2]-c[:,2])*(a[:,0]-c[:,0])+(c[:,0]-b[:,0])*(a[:,2]-c[:,2])
valid=np.abs(den)>1e-12
xmin=tri[:,:,0].min(1);xmax=tri[:,:,0].max(1);zmin=tri[:,:,2].min(1);zmax=tri[:,:,2].max(1)
cache={}
def rays(x,z):
 key=(round(float(x),9),round(float(z),9))
 if key in cache:return cache[key]
 ids=np.where(valid&(xmin<=x+1e-9)&(xmax>=x-1e-9)&(zmin<=z+1e-9)&(zmax>=z-1e-9))[0]
 aa,bb,cc=a[ids],b[ids],c[ids];dd=den[ids]
 u=((bb[:,2]-cc[:,2])*(x-cc[:,0])+(cc[:,0]-bb[:,0])*(z-cc[:,2]))/dd
 w=((cc[:,2]-aa[:,2])*(x-cc[:,0])+(aa[:,0]-cc[:,0])*(z-cc[:,2]))/dd
 hit=(u>=-1e-7)&(w>=-1e-7)&(u+w<=1+1e-7)
 ys=u[hit]*aa[hit,1]+w[hit]*bb[hit,1]+(1-u[hit]-w[hit])*cc[hit,1]
 ys=np.unique(np.round(ys,10));ys=ys[(ys>=-1e-6)&(ys<60)]
 cache[key]=ys;return ys
def face_ys(x,z):
 zz=min(max(z,.0001),55.17567495-.0001)
 yy=rays(x,zz)
 if len(yy)==0:yy=rays(x,max(20.5,min(54.5,zz)))
 if len(yy)==0:yy=rays(x,35)
 assert len(yy)>=1,(x,z,yy)
 return float(yy[0]),float(yy[-1])
def rear(x,z):return face_ys(x,z)[1]
def lower(x):
 ids=np.where((xmin<=x)&(xmax>=x))[0];zz=[]
 for i,j in [(0,1),(1,2),(2,0)]:
  pp,qq=tri[ids,i],tri[ids,j];d=qq[:,0]-pp[:,0]
  ok=(abs(d)>1e-12)&((pp[:,0]-x)*(qq[:,0]-x)<=0)
  zz.extend((pp[ok,2]+(qq[ok,2]-pp[ok,2])*(x-pp[ok,0])/d[ok]).tolist())
 return max(0.,min(zz)) if zz else 0.
def central_front(z):
 tplane=-.8-C*27-S*(z-23.6+S*27)/C
 roofplane=(z-23.6-32.3/C)/TAN-.8
 return max(tplane,roofplane)
def two_grid(outer,inner):
 nx,nz,_=outer.shape;n=nx*nz;vv=np.vstack([outer.reshape(-1,3),inner.reshape(-1,3)]);ff=[]
 def ix(i,j):return i*nz+j
 for i in range(nx-1):
  for j in range(nz-1):
   q=[ix(i,j),ix(i+1,j),ix(i+1,j+1),ix(i,j+1)]
   ff.extend([[q[0],q[1],q[2]],[q[0],q[2],q[3]]])
   q=[k+n for k in q[::-1]];ff.extend([[q[0],q[1],q[2]],[q[0],q[2],q[3]]])
 for i in range(nx-1):
  for j in [0,nz-1]:
   aa,bb=ix(i,j),ix(i+1,j);ff.extend([[aa,bb,bb+n],[aa,bb+n,aa+n]])
 for j in range(nz-1):
  for i in [0,nx-1]:
   aa,bb=ix(i,j),ix(i,j+1);ff.extend([[aa,bb,bb+n],[aa,bb+n,aa+n]])
 m=mesh(vv,ff);assert m.status()==md.Error.NoError,m.status()
 return m

# The rear curve is the real original face below its upper edge. Above that
# edge the rear limit is its vertical projection: no real BTTF surface exists
# there to intersect the specified sloping roof. This conflict is reported.
xs=np.unique(np.r_[np.linspace(-47.27,47.27,97),-45.3,45.3,-45.27,45.27,-33.6,-33,-30,-27,-26.4,-17,-15,0,15,17,26.4,27,30,33,33.6])
us=np.linspace(0,1,101)
front=[];back=[];top_rows=[]
for x in xs:
 ytop=rear(x,55.2);ztop=23.6+32.3/C+TAN*(ytop+.8)
 top_rows.append({'x':float(x),'projected_original_rear_top_y':ytop,'outer_roof_z':ztop})
 aa=[];bb=[]
 rowus=np.unique(np.r_[us,(23.6+C*32.3-S*27)/ztop,2/ztop])
 for u in rowus:
  z=ztop*u;aa.append([x,central_front(z),z]);bb.append([x,rear(x,z),z])
 front.append(aa);back.append(bb)
envelope=two_grid(np.array(front),np.array(back))
camera=tf(box([-44.97,0,0],[44.97,30,25]))
entry=tf(box([-45.27,-.5,-200],[45.27,30.3,25]))
original_modified=original-entry
under_shapes=[]
for lo,hi in [(-45.27,-17),(17,45.27)]:
 air=tf(box([lo,-200,-200],[hi,-2.5,25])) ^ box([-100,-200,2],[100,100,200])
 under_shapes.append(air)
nose=tf(box([-15,-200,-200],[15,-2.5,200]))
central=envelope-entry-nose-union(under_shapes)

# True 2mm front/top/bottom wing plates. Front normal offsets are calculated
# from the outer surface tangent grid; the top is capped at the stated55.2.
wing_parts=[];wing_envelopes=[];wing_surface_records=[]
for side,name in [(-1,'left'),(1,'right')]:
 xx=np.linspace(47.27,65,57)*side
 zz=np.linspace(0,1,81);out=[];backgrid=[]
 def wing_y(x,z):
  r=(abs(x)-47.27)/(65-47.27);w=r*r*(3-2*r)
  oldfront,_=face_ys(x,z)
  return central_front(z)*(1-w)+(oldfront-.1)*w
 for x in xx:
  row=[];brow=[];lo=lower(x)
  for u in zz:
   z=lo+(55.2-lo)*u;row.append([x,wing_y(x,z),z]);brow.append([x,rear(x,z),z])
  out.append(row);backgrid.append(brow)
 out=np.array(out);backgrid=np.array(backgrid)
 gx=np.gradient(out,axis=0);gu=np.gradient(out,axis=1)
 nn=np.cross(gx,gu);nn/=np.linalg.norm(nn,axis=2,keepdims=True)
 nn*=np.where(nn[:,:,1:2]<0,-1,1)
 inner=out+2*nn
 np.savez_compressed(P/f'wing_{name}_front_corresponding_surfaces.npz',outer=out,inner=inner,normal=nn)
 frontplate=two_grid(out,inner)
 yt=np.linspace(0,1,41);top=[];bot=[]
 for x in xx:
  tl=[];bl=[];lo=lower(x)
  for u in yt:
   tl.append([x,wing_y(x,55.2)*(1-u)+rear(x,55.2)*u,55.2])
   bl.append([x,wing_y(x,lo)*(1-u)+rear(x,lo)*u,lo])
  top.append(tl);bot.append(bl)
 top=np.array(top);bot=np.array(bot)
 topplate=two_grid(top,top+[0,0,-2])
 db=np.gradient(bot,axis=0);norm=np.cross(db,np.gradient(bot,axis=1));norm/=np.linalg.norm(norm,axis=2,keepdims=True);norm*=np.where(norm[:,:,2:3]<0,-1,1)
 botplate=two_grid(bot,bot+2*norm)
 wingenv=two_grid(out,backgrid)
 wings=union([frontplate,topplate,botplate]) ^ box([-72,-200,0],[72,60,55.2]) ^ wingenv
 wings=wings-entry
 wing_parts.append(wings);wing_envelopes.append(wingenv)
 wing_surface_records.append({'side':name,'front_nominal_normal_offset_mm':2.,'top_vertical_thickness_mm':2.,'bottom_normal_offset_mm':2.,'max_allowed_z':55.2,'front_offset_normal_measure_min_max':np.linalg.norm(inner-out,axis=2).min().item()})
 save('wing_'+name,wings);save('wing_'+name+'_envelope',wingenv)

# Stadium opening: the straight central run is48mm, radius10 inside and12
# outside, giving a2mm x2mm45-degree bevel through the2mm front plate.
def stadium(r,t):
 p=[]
 for cx,start in [(24,-math.pi/2),(-24,math.pi/2)]:
  for a in np.linspace(start,start+math.pi,65):p.append([cx+r*math.cos(a),15+r*math.sin(a),t])
 return np.array(p)
sections=[stadium(10,24.9),stadium(10,25),stadium(12,27),stadium(12,27.1)]
wv=np.concatenate(sections);wf=[];n=len(sections[0])
for j in range(3):
 for i in range(n):
  a=j*n+i;b=j*n+(i+1)%n;c=(j+1)*n+i;d=(j+1)*n+(i+1)%n;wf.extend([[a,b,c],[b,d,c]])
for j in [0,3]:
 for i in range(1,n-1):wf.append([j*n,j*n+i,j*n+i+1])
window=tf(mesh(wv,wf));central-=window

# Bottom cantilevers, routine preview dimensions: length8,width6,Ugap.6.
# They deliberately create narrow communication between the camera cavity
# and the lower pockets, and cannot be called hermetically closed pockets.
ucuts=[];hooks=[]
for x in [-30,30]:
 cuts=union([box([x-3.6,-3,-8],[x-3,-.4,.6]),box([x+3,-3,-8],[x+3.6,-.4,.6]),box([x-3.6,-3,0],[x+3.6,-.4,.6])])
 ucuts.append(tf(cuts));hooks.append(tf(box([x-3,-.52,-.8],[x+3,.3,0])))
central-=union(ucuts)
hooks=union(hooks)
tabs=[]
for lo,hi in [(-71.0974706,-67.8384247),(67.6905112,71.1061337)]:
 e=box([lo,140,23.2],[hi,159.0703299,55.2]);e-=box([lo-.1,151.5703299,26.2],[hi+.1,154.5703299,52.2]);tabs.append(e)
tabs=union(tabs)
new_shell=union([central,*wing_parts,hooks])
limitdata=np.load(P/'actual_original_forward_limit.npz')
actual_limit=M(md.Mesh64(vert_properties=np.ascontiguousarray(limitdata['v'],dtype=np.float64),tri_verts=np.ascontiguousarray(limitdata['f'],dtype=np.uint64)))
protected_side_mask=union([actual_limit,box([-80,-200,0],[80,0,100]),box([-80,-200,55.17567495],[80,100,100])])
new_shell=new_shell^protected_side_mask
central=central^protected_side_mask
wing_parts=[m^protected_side_mask for m in wing_parts]
for name,m in zip(['left','right'],wing_parts):save('wing_'+name,m)
front_final=union([original_modified,new_shell,tabs])
rawcomponents=front_final.decompose()
numerical_slivers=[m for m in rawcomponents if abs(m.volume())<1e-5]
positive_slivers=[m for m in numerical_slivers if m.volume()>0]
if positive_slivers:new_shell-=union(positive_slivers)
large_positive=[m for m in rawcomponents if m.volume()>=1e-5]
large_negative=[m for m in rawcomponents if m.volume()<=-1e-5]
assert len(large_positive)==1
positive_air=[]
for air in large_negative:
 am=air.to_mesh64();positive_air.append(mesh(np.array(am.vert_properties)[:,:3],np.array(am.tri_verts)[:,::-1]))
front_final=large_positive[0]-union(positive_air)
components_debug=[{'volume':float(m.volume()),'bounds':list(m.bounding_box())} for m in front_final.decompose()]
positive=[m for m in front_final.decompose() if m.volume()>1e-8]
negative=[m for m in front_final.decompose() if m.volume()<-1e-8]
assert front_final.status()==md.Error.NoError and len(positive)==1,(front_final.status(),components_debug)
report={'inspection_only':True,'camera_transform':T.tolist(),'original_source':str(SOURCE),'original_source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'original':save('original',original),'original_modified':save('original_modified',original_modified),'camera':save('camera',camera),'camera_entry_sweep_cut':save('camera_entry_sweep_cut',entry),'central_envelope':save('central_envelope',envelope),'central_shell':save('central_shell',central),'new_shell':save('new_shell',new_shell),'hooks':save('hooks',hooks),'ucuts':save('ucuts',union(ucuts)),'front_tabs':save('front_tabs',tabs),'front_unified_preview':save('front_unified_preview',front_final),'wing_surfaces':wing_surface_records,'roof_rear_rows':top_rows}
save('window_cut',window)
save('shell_added',new_shell-original)
air_report={}
for i,name in enumerate(['left','right']):
 air=(under_shapes[i]^envelope)-original-new_shell
 air_report['under_'+name]=save('air_under_'+name,air)
 air=(wing_envelopes[i]-original)-new_shell
 air_report['wing_'+name]=save('air_wing_'+name,air)
report['air_regions']=air_report
report['positive_connected_outer_solids']=len(positive)
report['negative_sealed_air_shells']=len(negative)
report['numerical_disconnected_slivers_removed_mm3']=sum(abs(float(m.volume())) for m in numerical_slivers)
for i,m in enumerate(negative):
 a=m.to_mesh64();vv=np.array(a.vert_properties)[:,:3];ff=np.array(a.tri_verts)
 air=mesh(vv,ff[:,::-1]);save('air_sealed_'+('left' if vv[:,0].mean()<0 else 'right'),air)
report.update({'camera_size_width_h_t_mm':[89.94,30,25],'camera_tilt_deg':20,'cavity_x_h_mm':[[-45.27,-.5],[45.27,30.3]],'outer_tube_x_h_mm':[[-47.27,-2.5],[47.27,32.3]],'front_wall_inner_outer_t_mm':[25,27],'front_top_outer_yz_mm':[-.8-S*32.3-C*27,23.6+C*32.3-S*27],'nose_width_mm':30,'floor_z_mm':[0,2],'normal_wall_nominal_mm':2,'window_inside_width_height_mm':[68,20],'window_outside_width_height_mm':[72,24],'window_center_x_h_mm':[0,15],'window_bevel_deg':45,'cantilever_length_width_gap_mm':[8,6,.6],'hook_height_mm':.8,'hook_root_embedded_mm':.02,'hook_x_centers_mm':[-30,30],'m2_and_eject_holes':'Removed by starting from true original source; no oldholes reapplied.','original_leg_shortening_mm':[0,0],'ear_height_slot_mm':[32,26,3],'preserved_ear_thickness_left_right_mm':[3.2590459,3.4156225],'volume_cm3':float(front_final.volume())/1000,'maximum_roof_z_mm':max(q['outer_roof_z'] for q in top_rows),'frontmost_y_mm':float(front_final.bounding_box()[1]),'new_geometry_after_original_subtraction':save('added_material',union([new_shell,tabs])-original),'known_unmet_or_conflicting_requirements':[
 {'requirement':'Z<=60','observation':'Fixed parallel roof must extend above60 near camera ends when its rear edge reaches the vertically projected original rear upper face. NoZ60 clipping or camera motion was applied.','actual_max_z_mm':max(q['outer_roof_z'] for q in top_rows)},
 {'requirement':'Wing top continuously follows central roof, wingZ<=55.2','observation':'Wing top is kept at55.2 and joins the central sidewall; above55.2 the sloped central roof cannot continuously join a wing obeying55.2.'},
 {'requirement':'Lower spaces closed while bottom wall hasUslots','observation':'The two.6mmUcuts connect lower air regions to camera cavity. Supports cannot be presumed removable through these narrowcuts.'},
 {'requirement':'Rear roof ends on actual BTTF face','observation':'Roof is already above the original55.1757mm top before reaching the face; no actual face exists there. Preview uses vertical projection of original rear upper edge and labels it explicitly.'}
],'not_yet_checked':['Global maximum fused-junction thickness','Actual source-surface interpolation penetration','Camera retreat collision excludinghooks','Official STP optical registration','Nose clearance to registered head','Slicer support and physical hookdeflection']})
(P/'geometry_values.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps({'front':report['front_unified_preview'],'volume_cm3':report['volume_cm3'],'max_roof_z':report['maximum_roof_z_mm'],'frontmost_y':report['frontmost_y_mm'],'air':air_report},indent=2))
