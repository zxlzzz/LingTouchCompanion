"""Read-only sampled checks. Never modifies the inspection geometry."""
from pathlib import Path
import json,math,time,hashlib
import numpy as np
import manifold3d as md
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree
P=Path(__file__).resolve().parent;M=md.Manifold
def load(name):
 a=np.load(P/(name+'.npz'));return M(md.Mesh64(vert_properties=np.ascontiguousarray(a['v'],dtype=np.float64),tri_verts=np.ascontiguousarray(a['f'],dtype=np.uint64)))
front=load('front_unified_preview');original=load('original');shell=load('new_shell');hooks=load('hooks')
C=math.cos(math.radians(20));S=math.sin(math.radians(20));R=np.array([[1,0,0],[0,-S,-C],[0,C,-S]],float);offset=np.array([0,-.8,23.6])
report={'method_limits':'Finite surface/ray/local-thickness samples; not a proof of global thickness or all-view visibility.'}
report['front_mesh_sha256']=hashlib.sha256((P/'front_unified_preview.npz').read_bytes()).hexdigest()
raw=np.load(P/'original_reference.npz');rawtri=raw['v'][raw['f']]
ra,rb,rc=rawtri[:,0],rawtri[:,1],rawtri[:,2]
rd=(rb[:,2]-rc[:,2])*(ra[:,0]-rc[:,0])+(rc[:,0]-rb[:,0])*(ra[:,2]-rc[:,2])
rx0=rawtri[:,:,0].min(1);rx1=rawtri[:,:,0].max(1);rz0=rawtri[:,:,2].min(1);rz1=rawtri[:,:,2].max(1)
def exact_source_ys(x,z):
 ids=np.where((abs(rd)>1e-15)&(rx0<=x+1e-9)&(rx1>=x-1e-9)&(rz0<=z+1e-9)&(rz1>=z-1e-9))[0]
 aa,bb,cc=ra[ids],rb[ids],rc[ids];dd=rd[ids]
 u=((bb[:,2]-cc[:,2])*(x-cc[:,0])+(cc[:,0]-bb[:,0])*(z-cc[:,2]))/dd
 w=((cc[:,2]-aa[:,2])*(x-cc[:,0])+(aa[:,0]-cc[:,0])*(z-cc[:,2]))/dd
 good=(u>=-1e-8)&(w>=-1e-8)&(u+w<=1+1e-8)
 yy=u[good]*aa[good,1]+w[good]*bb[good,1]+(1-u[good]-w[good])*cc[good,1]
 return yy[yy<60]

# Actual source intersections, not the interpolated modeling rear field.
a=shell.to_mesh64();v=np.array(a.vert_properties)[:,:3];f=np.array(a.tri_verts)
points=np.vstack([v,(v[f[:,0]]+v[f[:,1]]+v[f[:,2]])/3])
points=points[(points[:,1]>=0)&(points[:,2]>=.001)&(points[:,2]<=55.17567495-.001)&(np.abs(points[:,0])<=65)]
if len(points)>30000:points=points[np.linspace(0,len(points)-1,30000,dtype=int)]
over=[];no_face=0;raw_fallbacks=0;glancing_corrected=0
for p in points:
 hits=original.ray_cast((float(p[0]),-100,float(p[2])),(float(p[0]),60,float(p[2])))
 yy=[h.position[1] for h in hits if h.position[1]<60]
 if len(yy)<2:
  yy=exact_source_ys(p[0],p[2]);raw_fallbacks+=1
  if len(yy)==0:no_face+=1;continue
 d=float(p[1]-max(yy))
 if d>1e-7:
  raw_y=exact_source_ys(p[0],p[2]);raw_fallbacks+=1
  if len(raw_y):
   old=d;d=float(p[1]-max(raw_y));yy=raw_y
   if old>1e-7 and d<=1e-7:glancing_corrected+=1
 if d>1e-7:over.append((d,p.tolist(),max(yy)))
over.sort(key=lambda x:x[0],reverse=True)
report['original_face_side_material_samples']={'samples':len(points),'no_actual_face_at_sample':no_face,'overrun_samples':len(over),'maximum_rear_y_overrun_mm':0 if not over else over[0][0],'maximum_sample_xyz_mm':None if not over else over[0][1],'actual_source_rear_y_at_max':None if not over else over[0][2],'raw_triangle_fallback_queries':raw_fallbacks,'false_glancing_overrun_candidates_corrected':glancing_corrected,'glancing_method':'Grazing raw source surface points can be omitted by solid ray entry/exit filtering. Missing/suspect hits are recomputed directly against unchanged original triangles inXZ barycentric coordinates.','top_over_original_height':'No actual original face exists above55.17567495; excluded from this finite comparison and already recorded as construction conflict.'}

# Camera surfaces viewed along principal and diagonal directions. If an
# unobstructed ray exits by the face-side aperture it is explicitly exempt.
def stadium(x,h,r):return max(abs(x)-24,0)**2+(h-15)**2<=r*r+1e-8
dirs=[]
for x in [-1,0,1]:
 for h in [-1,0,1]:
  for t in [-1,0,1]:
   d=np.array([x,h,t],float)
   if np.linalg.norm(d):dirs.append(d/np.linalg.norm(d))
dirs.extend([R.T@np.array([0,0,1]),R.T@np.array([0,0,-1]),R.T@np.array([0,-1,0]),R.T@np.array([0,1,0])])
tested=blocked=viawindow=viarear=unexpected=0;examples=[]
surfaces=[]
for fixed,axis,normal in [(-44.97,0,[-1,0,0]),(44.97,0,[1,0,0]),(0,1,[0,-1,0]),(30,1,[0,1,0]),(25,2,[0,0,1])]:
 other=[i for i in range(3) if i!=axis]
 span=[[-44.95,44.95],[.02,29.98],[.02,24.98]]
 for aa in np.linspace(*span[other[0]],9):
  for bb in np.linspace(*span[other[1]],9):
   p=np.zeros(3);p[axis]=fixed;p[other[0]]=aa;p[other[1]]=bb
   surfaces.append((p,np.array(normal,float)))
for p,n in surfaces:
 for d in dirs:
  if np.dot(n,d)<=.05:continue
  origin=R@(p+d*.001)+offset;end=origin+R@d*300
  tested+=1
  hits=front.ray_cast(tuple(origin),tuple(end))
  if hits:blocked+=1;continue
  if d[2]<-1e-9:viarear+=1;continue
  if d[2]>1e-9:
   p25=p+d*((25-p[2])/d[2]);p27=p+d*((27-p[2])/d[2])
   if stadium(p25[0],p25[1],10) and stadium(p27[0],p27[1],12):viawindow+=1;continue
  unexpected+=1
  if len(examples)<10:examples.append({'camera_point_x_h_t':p.tolist(),'outgoing_direction_x_h_t':d.tolist()})
report['sampled_external_visibility']={'tested':tested,'blocked_by_front_part':blocked,'clear_through_specified_window':viawindow,'clear_toward_face_side_aperture':viarear,'clear_unexpected':unexpected,'unexpected_examples':examples,'rear_classification':'Negative camera-axis component and no shell hit; face-side aperture exemption. Finite rays do not prove arbitrary continuous views.'}

# Inscribed-sphere sampling is a useful local wall-thickness metric at
# corners. Casting along a thin plate end-cap normal would measure plate
# length rather than wall thickness, so that misleading metric is avoided.
body=shell-hooks;me=body.to_mesh64();vv=np.array(me.vert_properties)[:,:3];ff=np.array(me.tri_verts,dtype=int)
bvh=BVHTree.FromPolygons(vv.tolist(),ff.tolist(),all_triangles=True)
tn=np.cross(vv[ff[:,1]]-vv[ff[:,0]],vv[ff[:,2]]-vv[ff[:,0]])
vn=np.zeros_like(vv)
for k in range(3):np.add.at(vn,ff[:,k],tn)
vn/=np.maximum(np.linalg.norm(vn,axis=1,keepdims=True),1e-30)
ids=np.linspace(0,len(vv)-1,min(1000,len(vv)),dtype=int)
best=(0,None);inside_candidates=0
for r in [1.,1.5,2.2]:
 for p in vv[ids]-r*vn[ids]:
  q,n,i,dist=bvh.find_nearest(Vector(p))
  if q is None or np.dot(p-np.array(q),np.array(n))>=-1e-8:continue
  inside_candidates+=1
  if dist>best[0]:
   hits=body.ray_cast(tuple(p),tuple(p+np.array([0,0,200.])))
   crossing=np.unique(np.round([h.position[2] for h in hits],9))
   if len(crossing)%2==1:best=(float(dist),p.copy())
inside_exact=False
if best[1] is not None:
 p=best[1];hits=body.ray_cast(tuple(p),tuple(p+np.array([0,0,200.])))
 inside_exact=len(np.unique(np.round([h.position[2] for h in hits],9)))%2==1
report['sampled_local_thickness']={'method':'Twice nearest boundary distance at sampled interior points; normal vertex offsets including joins. Finite sampling, not global maximum proof. Hooks excluded.','candidates':len(ids)*3,'interior_nearest_normal_samples':inside_candidates,'largest_sampled_inscribed_radius_mm':best[0],'largest_sampled_local_thickness_mm':2*best[0],'sample_xyz_mm':None if best[1] is None else best[1].tolist(),'maximum_sample_inside_verified_by_ray_parity':inside_exact,'over3mm_proven_sample':bool(inside_exact and best[0]>1.5)}
report['actual_face_limit_construction']=json.loads((P/'actual_original_forward_limit.json').read_text())
report['protection_claim_scope']='All newY>0 shell material below the original upperZ bound is intersected with the forward envelope of actual rear-facing original triangles; the original surface coordinates are retained. NewY<=0 material remains in front of every original face (original minimumY0), including the required tube bottom above the nose passage. Finite actual-source ray samples separately measure residual numerical overrun. Above the original top the declared projected rear boundary is used; no real BTTF face exists there.'
(P/'surface_visibility_thickness_checks.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report,indent=2))
