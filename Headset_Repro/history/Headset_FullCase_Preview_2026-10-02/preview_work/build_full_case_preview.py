"""Preview-only full-case geometry. No 3MF/STL manufacturing export."""
from pathlib import Path
import json, math
import numpy as np
import manifold3d as md
import trimesh
ROOT=Path(__file__).resolve().parents[1];BASE=ROOT.parent;W=ROOT/'preview_work'
W.mkdir(parents=True,exist_ok=True)
M=md.Manifold;C,S=math.cos(math.radians(20)),math.sin(math.radians(20))
T=np.eye(4);T[:3,:3]=[[1,0,0],[0,-S,-C],[0,C,-S]];T[:3,3]=[0,-.8,23.6]
def box(lo,hi):
 lo=np.array(lo,float);hi=np.array(hi,float)
 return M.cube(tuple(hi-lo)).translate(tuple(lo))
def tf(m):return m.transform(T[:3,:4])
def union(a):return M.batch_boolean(a,md.OpType.Add)
def save(name,m):
 me=m.to_mesh64();np.savez_compressed(W/(name+'.npz'),v=np.array(me.vert_properties)[:,:3],f=np.array(me.tri_verts))
def raw(name,v,f):np.savez_compressed(W/(name+'.npz'),v=v,f=f)
def from_mesh(v,f):
 return M(md.Mesh64(vert_properties=np.ascontiguousarray(v,dtype=np.float64),tri_verts=np.ascontiguousarray(f,dtype=np.uint64)))
source=np.load(BASE/'Headset_Prop_Stage1_2026-10-02/reference_normal_mesh.npz')
v=source['vertices'].copy()+[0,73.53516495,27.587837475];f=source['faces'];tri=v[f]
original=from_mesh(v,f);assert original.status()==md.Error.NoError
raw('original_reference',v,f)
# Grid rear coordinates come from intersections with original triangles.
# Source vertices and face indices are never deformed or remeshed.
a,b,c=tri[:,0],tri[:,1],tri[:,2]
den=(b[:,2]-c[:,2])*(a[:,0]-c[:,0])+(c[:,0]-b[:,0])*(a[:,2]-c[:,2])
valid=np.abs(den)>1e-12
xmin=tri[:,:,0].min(axis=1);xmax=tri[:,:,0].max(axis=1)
zmin=tri[:,:,2].min(axis=1);zmax=tri[:,:,2].max(axis=1)
def ray_ys(x,z):
 ids=np.where(valid&(xmin<=x+1e-9)&(xmax>=x-1e-9)&(zmin<=z+1e-9)&(zmax>=z-1e-9))[0]
 aa,bb,cc=a[ids],b[ids],c[ids];dd=den[ids]
 p=((bb[:,2]-cc[:,2])*(x-cc[:,0])+(cc[:,0]-bb[:,0])*(z-cc[:,2]))/dd
 q=((cc[:,2]-aa[:,2])*(x-cc[:,0])+(aa[:,0]-cc[:,0])*(z-cc[:,2]))/dd
 hit=(p>=-1e-7)&(q>=-1e-7)&(p+q<=1+1e-7)
 ys=p[hit]*aa[hit,1]+q[hit]*bb[hit,1]+(1-p[hit]-q[hit])*cc[hit,1]
 return np.unique(np.round(ys,10))
def rear_boundary(x,z):
 ys=ray_ys(x,min(z,55.17567495-1e-7))
 ys=ys[(ys>=-1e-6)&(ys<60)]
 if len(ys)==0:ys=ray_ys(x,30)
 y0=float(ys[0]);y1=float(ys[1]) if len(ys)>1 else y0
 return y0+min(.15,max(0,(y1-y0)/2))
def original_lower(x):
 ids=np.where((xmin<=x)&(xmax>=x))[0];zz=[]
 for i,j in [(0,1),(1,2),(2,0)]:
  p,q=tri[ids,i],tri[ids,j];d=q[:,0]-p[:,0]
  good=(abs(d)>1e-12)&((p[:,0]-x)*(q[:,0]-x)<=0)
  zz.extend((p[good,2]+(q[good,2]-p[good,2])*(x-p[good,0])/d[good]).tolist())
 return min(zz) if zz else 0
front_upper=(T@np.array([0,30,25,1]))[1:3]
def central_front(z):
 return -.8-C*25-S*(z-23.6+S*25)/C if z<=front_upper[1] else front_upper[0]
# Wing join is a declared preview choice. It follows measured original surfaces.
xs=np.unique(np.r_[np.linspace(-65,65,131),-47.3,47.3,-13,13,-45.27,45.27])
us=np.unique(np.r_[np.linspace(0,1,81),front_upper[1]/55.2])
nz=len(us);vv=[];nxs=len(xs)
for side in [0,1]:
 for x in xs:
  low=original_lower(x) if abs(x)>47.3 else 0
  for u in us:
   z=low+(55.2-low)*u;yback=rear_boundary(x,z)
   if side==1:y=yback
   elif abs(x)<=47.3:y=central_front(z)
   else:
    t=(abs(x)-47.3)/(65-47.3);w=1-(3*t*t-2*t*t*t)
    yf=yback-.15;y=yf-w*(yf-central_front(z))
   vv.append([x,y,z])
vv=np.array(vv);ff=[];offset=nxs*nz
def ix(side,i,j):return side*offset+i*nz+j
for i in range(nxs-1):
 for j in range(nz-1):
  for side in [0,1]:
   quad=[ix(side,i,j),ix(side,i+1,j),ix(side,i+1,j+1),ix(side,i,j+1)]
   if side==0:quad=quad[::-1]
   ff.extend([[quad[0],quad[1],quad[2]],[quad[0],quad[2],quad[3]]])
for j in range(nz-1):
 for i in [0,nxs-1]:
  quad=[ix(0,i,j),ix(0,i,j+1),ix(1,i,j+1),ix(1,i,j)]
  ff.extend([[quad[0],quad[1],quad[2]],[quad[0],quad[2],quad[3]]])
for i in range(nxs-1):
 for j in [0,nz-1]:
  quad=[ix(0,i,j),ix(0,i+1,j),ix(1,i+1,j),ix(1,i,j)]
  ff.extend([[quad[0],quad[1],quad[2]],[quad[0],quad[2],quad[3]]])
mesh=trimesh.Trimesh(vv,np.array(ff),process=True);trimesh.repair.fix_normals(mesh,multibody=True)
case_envelope=from_mesh(mesh.vertices,mesh.faces)
assert case_envelope.status()==md.Error.NoError,(case_envelope.status(),mesh.is_watertight)
cavity=tf(box([-45.27,-.5,0],[45.27,30.3,100]))
nose_cut=tf(box([-13,-200,-200],[13,-2.5,200]))
# Cut the nose passage only in added material; original nose remains untouched.
case=case_envelope-cavity-nose_cut
A=np.array([[1,0,0,0],[0,0,1,30.3],[0,-1,0,12.5]],float)
m2=tf(M.cylinder(80,.85,circular_segments=64).transform(A))
E=np.array([[1,0,0,0],[0,-1,0,15],[0,0,-1,.01]],float)
eject=tf(M.cylinder(60,2,circular_segments=80).transform(E))
case=case-m2-eject
original_modified=original-eject
added=case-original
camera=tf(box([-44.97,0,0],[44.97,30,25]))
save('case_material',added);save('case_envelope',case_envelope)
save('camera',camera);save('original_modified',original_modified)
tabs=[]
for lo,hi in [(-71.0974706,-67.8384247),(67.6905112,71.1061337)]:
 e=box([lo,140,33.2],[hi,159.0703299,55.2])
 e-=box([lo-.1,151.5703299,36.2],[hi+.1,154.5703299,52.2]);tabs.append(e)
tabs=union(tabs);save('front_tabs',tabs)
front=union([original_modified,case,tabs]);save('front_unified_preview',front)
py=190.
pocket=box([-60.8,py,0],[60.8,py+19.6,47])-box([-58.8,py+2,2],[58.8,py+17.6,47.1])
pocket-=box([58.7,py+4.3,12],[60.9,py+15.3,47.1])
for sign in [-1,1]:
 lo,hi=(60.6,72.8) if sign>0 else (-72.8,-60.6)
 e=box([lo,py,25],[hi,py+2,47]);cx=sign*66.8
 e-=box([cx-1.5,py-.1,28],[cx+1.5,py+2.1,44]);pocket+=e
pocket+=M.sphere(1,48).scale((1,.8,.8)).translate((0,py+2,45.5))
save('pocket',pocket);save('battery',box([-58.5,py+2.3,2],[58.5,py+17.3,49]))
info={'preview_only':True,'no_3mf_or_stl_export':True,'wing_join_abs_x':65,
      'wing_transition':'Smooth measured original front-surface offset from absX47.3 to65; preview choice.',
      'cavity_width_height_axialdepth':[90.54,30.8,25],
      'outer_central_width':94.6,'sidewall':2.03,'m2':[1.7,12.5],
      'source_original_bounds':np.array(original.bounding_box()).tolist(),
      'case_material_bounds':np.array(added.bounding_box()).tolist(),
      'front_bounds':np.array(front.bounding_box()).tolist(),
      'front_components':len(front.decompose()),'front_status':str(front.status()),
      'original_modification':'Only analytic diameter4 push-out hole cut; nose cut applied to added material only.',
      'pocket_bump_inward':.8,'head_position_is_trial':True,'pocket_y_schematic':190}
(ROOT/'preview_geometry_values.json').write_text(json.dumps(info,indent=2),encoding='utf8')
print(json.dumps(info,indent=2))
