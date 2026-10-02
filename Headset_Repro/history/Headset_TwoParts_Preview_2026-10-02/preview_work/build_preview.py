"""Preview geometry only. Not a manufacturing export or an approved design."""
from pathlib import Path
import json, math
import numpy as np
import manifold3d as md
import trimesh

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT.parent
OUT=ROOT/'preview_work'
M=md.Manifold
C,S=math.cos(math.radians(20)),math.sin(math.radians(20))
# Local axes: across, camera up, optical forward. Right handed.
T=np.eye(4);T[:3,:3]=[[1,0,0],[0,-S,-C],[0,C,-S]];T[:3,3]=[0,-.8,23.6]
def box(lo,hi):
 lo=np.array(lo,float);hi=np.array(hi,float)
 return M.cube(tuple(hi-lo)).translate(tuple(lo))
def transform(m):return m.transform(T[:3,:4])
def yz_prism(poly,xlo,xhi):
 # Cross section localXY=(worldY,worldZ), extrusionZ=worldX.
 poly=np.asarray(poly,dtype=float)
 if np.sum(poly[:,0]*np.roll(poly[:,1],-1)-poly[:,1]*np.roll(poly[:,0],-1))<0:poly=poly[::-1].copy()
 p=M.extrude(md.CrossSection([poly]),xhi-xlo)
 A=np.array([[0,0,1,xlo],[1,0,0,0],[0,1,0,0]],float)
 return p.transform(A)
def union(p):return M.batch_boolean(p,md.OpType.Add)
def mesh_save(name,m):
 a=m.to_mesh();np.savez_compressed(OUT/(name+'.npz'),v=np.array(a.vert_properties)[:,:3],f=np.array(a.tri_verts))
def raw_save(name,v,f):np.savez_compressed(OUT/(name+'.npz'),v=v,f=f)
OUT.mkdir(parents=True,exist_ok=True)
r=np.load(BASE/'Headset_Prop_Stage1_2026-10-02/reference_normal_mesh.npz')
v=r['vertices'].copy()+[0,73.53516495,27.587837475];f=r['faces']
raw_save('original',v,f)

camera=transform(box([-44.97,0,0],[44.97,30,25]))
mesh_save('camera',camera)
outer=box([-47.27,-2.5,-2],[47.27,32.3,15])
void=box([-45.27,-.5,0],[45.27,30.3,15.01])
tube=transform(outer-void)
# Above-tube fill bounded by the front mouth plane and original front datum.
ur=(T@np.array([0,32.3,-2,1]))[1:3]
uf=(T@np.array([0,32.3,15,1]))[1:3]
mouth_top=((-.8-C*15)-S*(55.2-23.6+S*15)/C)
roof=yz_prism([ur.tolist(),uf.tolist(),[mouth_top,55.2],[0,55.2]],-47.27,47.27)
# Roof behind rear plane is the required gap-fill area, shown separately.
hole_local=M.cylinder(35,.85,circular_segments=64).translate((0,30.3,7.5))
# Cylinder nativeZ -> local height axis, starting on cavity top.
A=np.array([[1,0,0,0],[0,0,1,30.3],[0,-1,0,7.5]],float)
hole=transform(M.cylinder(35,.85,circular_segments=64).transform(A))
socket=union([tube,roof])-hole
mesh_save('socket',socket)
# Required connector is a visual diagnostic. Its outer endpoint is read from
# original mesh rays; no source surface is reconstructed or replaced.
tri=v[f]
def front_y(x,z):
 # Triangle barycentrics in XZ, then first positive ray hit in Y.
 a,b,c=tri[:,0],tri[:,1],tri[:,2]
 den=(b[:,2]-c[:,2])*(a[:,0]-c[:,0])+(c[:,0]-b[:,0])*(a[:,2]-c[:,2])
 ok=np.abs(den)>1e-12;w0=np.zeros(len(tri));w1=w0.copy()
 w0[ok]=((b[ok,2]-c[ok,2])*(x-c[ok,0])+(c[ok,0]-b[ok,0])*(z-c[ok,2]))/den[ok]
 w1[ok]=((c[ok,2]-a[ok,2])*(x-c[ok,0])+(a[ok,0]-c[ok,0])*(z-c[ok,2]))/den[ok]
 hit=ok&(w0>=-1e-8)&(w1>=-1e-8)&(w0+w1<=1+1e-8)
 ys=w0[hit]*a[hit,1]+w1[hit]*b[hit,1]+(1-w0[hit]-w1[hit])*c[hit,1]
 return float(ys.min()) if len(ys) else float('nan')
# Ruled front-fill diagnostic at two Z levels. It is not used to claim an exact
# mesh union. Bottom follows the rear underside at Z21.9348; no fill below it.
zs=[float((T@np.array([0,-2.5,-2,1]))[2]),55.17567495-.15]
xs=np.linspace(-47.27,47.27,101)
points=[]
for z in zs:
 for x in xs:
  y=front_y(x,z)
  if z==zs[0]:
   for _ in range(2):
    z_at_curve=23.6+(-2.5+S*(y+.8))/C
    y=front_y(x,z_at_curve)
   points.append([x,y,z_at_curve])
  else:points.append([x,y,z])
curve=np.array(points).reshape(2,-1,3)
# Both rear socket corners are on t=-2 plane; its Y varies with Z.
rear_y=lambda z: -.8+2/C-S*(z-23.6)/C
vv=[];ff=[]
for i in range(len(xs)-1):
 p=[curve[0,i],curve[0,i+1],curve[1,i+1],curve[1,i],
    [xs[i],rear_y(zs[0]),zs[0]],[xs[i+1],rear_y(zs[0]),zs[0]],
    [xs[i+1],rear_y(zs[1]),zs[1]],[xs[i],rear_y(zs[1]),zs[1]]]
 o=len(vv);vv.extend(p)
 for q in [(0,1,2),(0,2,3),(4,6,5),(4,7,6),(0,4,5),(0,5,1),
           (3,2,6),(3,6,7),(0,3,7),(0,7,4),(1,5,6),(1,6,2)]:ff.append([o+k for k in q])
raw_save('required_fill_diagnostic',np.array(vv),np.array(ff))
# Ear roots overlap the rounded tips; source mesh is displayed intact.
tabs=[]
for lo,hi in [(-71.0974706,-67.8384247),(67.6905112,71.1061337)]:
 e=box([lo,140,33.2],[hi,159.0703299,55.2])
 e-=box([lo-.1,151.5703299,36.2],[hi+.1,154.5703299,52.2])
 tabs.append(e)
mesh_save('front_tabs',union(tabs))
# Rear pocket placement Y190 is a schematic band layout; no fitted claim.
py=190.
body=box([-60.8,py,0],[60.8,py+19.6,47])
body-=box([-58.8,py+2,2],[58.8,py+17.6,47.1])
body-=box([58.7,py+4.3,12],[60.9,py+15.3,47.1])
for sign in [-1,1]:
 lo,hi=(60.6,72.8) if sign>0 else (-72.8,-60.6)
 e=box([lo,py,25],[hi,py+2,47])
 cx=sign*66.8
 e-=box([cx-1.5,py-.1,28],[cx+1.5,py+2.1,44])
 body+=e
bump=M.sphere(1,32).scale((1,.4,.8)).translate((0,py+2,45.5))
body+=bump
mesh_save('pocket',body)
mesh_save('battery',box([-58.5,py+2.3,2],[58.5,py+17.3,49]))
info={'preview_only':True,'original_mesh_unchanged':True,'source_vertices':len(v),
      'source_faces':len(f),'camera_edges_yz':{},'pocket_y_placement_schematic':py,
      'socket_bounds':np.array(socket.bounding_box()).tolist(),
      'rear_ears_width_increase_per_side':12,'rear_ear_thickness':2,
      'front_tab_thickness_left':3.2590459,'front_tab_thickness_right':3.4156225,
      'no_manufacturing_union_or_printable_exports_created':True}
for name,q,t in [('rear_lower',0,0),('front_lower',0,25),('front_upper',30,25),('rear_upper',30,0)]:
 info['camera_edges_yz'][name]=(T@np.array([0,q,t,1]))[1:3].tolist()
(ROOT/'preview_geometry_values.json').write_text(json.dumps(info,indent=2),encoding='utf8')
print(json.dumps(info,indent=2))
