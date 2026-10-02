"""Construct and optimize all glass.md connections, then verify exact cubic curvature extrema."""
import os,sys,json,math,time
os.environ['OPENBLAS_NUM_THREADS']='1';os.environ['OMP_NUM_THREADS']='1'
from pathlib import Path
import numpy as np
from scipy.interpolate import CubicSpline
from scipy.optimize import least_squares
from scipy.integrate import quad
P=Path(__file__).parent;D=P.parent/sys.argv[1];design=json.loads((D/'design_data.json').read_text(encoding='utf-8'));meta=json.load(open(D/'working_objects.json'));arr=np.load(D/'working_meshes.npz');K=design['key'];L=design['leads'];results={}
ob=[]
for n,m in meta.items():
 if not m['category'].startswith('component') or n=='CS30__OFFICIAL_STEP_MESH' or n.startswith('REF_'):continue
 owner=m['owner'];R=np.array(design['poses'][owner]['matrix']) if owner in design['poses'] else np.eye(4);inv=np.linalg.inv(R);v=arr[n+'__v']@inv[:3,:3].T+inv[:3,3];lo=v.min(0);hi=v.max(0);center=R[:3,:3]@((lo+hi)/2)+R[:3,3]
 ob.append(dict(name=n,center=center,rotation=R[:3,:3],half=(hi-lo)/2))
centers=np.array([o['center'] for o in ob]);rotations=np.array([o['rotation'] for o in ob]);half=np.array([o['half'] for o in ob])
def unit(x):return np.array(x,float)/max(np.linalg.norm(x),1e-12)
def body_dist(points):
 local=np.einsum('nbi,bij->nbj',points[:,None,:]-centers[None,:,:],rotations);q=np.abs(local)-half
 return np.linalg.norm(np.maximum(q,0),axis=2)+np.minimum(np.max(q,axis=2),0)
def head_dist(points):
 all=[]
 for c,r in [((0,0,0),(78,96,116)),((77,-15,-15),(8,17,27)),((-77,-15,-15),(8,17,27)),((0,92,-18),(12,20,23))]:
  q=points-c;rho=np.linalg.norm(q/r,axis=1);all.append((rho-1)*min(r))
 return np.min(all,axis=0)
def line(a,b):a=np.array(a);b=np.array(b);return np.array([a,a+(b-a)/3,a+2*(b-a)/3,b])
def exact_radius(seg):
 from numpy.polynomial import polynomial as pol
 p0,p1,p2,p3=np.array(seg);v=np.array([3*(p1-p0),6*(p2-2*p1+p0),3*(p3-3*p2+3*p1-p0)]);a=np.array([v[1],2*v[2]])
 cross=[]
 for i,j in [(1,2),(2,0),(0,1)]:cross.append(pol.polysub(pol.polymul(v[:,i],a[:,j]),pol.polymul(v[:,j],a[:,i])))
 N=np.array([0.]);S=np.array([0.])
 for c in cross:N=pol.polyadd(N,pol.polymul(c,c))
 for k in range(3):S=pol.polyadd(S,pol.polymul(v[:,k],v[:,k]))
 extrema=pol.polysub(pol.polymul(pol.polyder(N),S),3*pol.polymul(N,pol.polyder(S)))
 while len(extrema)>1 and abs(extrema[-1])<1e-13:extrema=extrema[:-1]
 roots=pol.polyroots(extrema) if len(extrema)>1 else []
 ts=[0.,1.]+[float(r.real) for r in roots if abs(r.imag)<1e-6 and 0<r.real<1]
 ts+=list(np.linspace(0,1,101));curv=[]
 for t in ts:
  ss=max(float(pol.polyval(t,S)),1e-18);nn=max(float(pol.polyval(t,N)),0);curv.append(math.sqrt(nn/ss**3))
 return 1/max(max(curv),1e-12)
def metrics(segs):
 length=0
 for c in segs:
  def speed(t):return np.linalg.norm(3*((1-t)**2*(c[1]-c[0])+2*(1-t)*t*(c[2]-c[1])+t*t*(c[3]-c[2])))
  length+=quad(speed,0,1,epsabs=1e-7)[0]
 return dict(length_mm=length,min_radius_mm=min(exact_radius(c) for c in segs))
def sample(segs,n=60):
 t=np.linspace(0,1,n)[:,None];return np.vstack([(1-t)**3*c[0]+3*(1-t)**2*t*c[1]+3*(1-t)*t*t*c[2]+t**3*c[3] for c in segs])
def solve(name,start,end,da,db,r,minr,hints=[],target=None,margin=1.18):
 start=np.array(start,float);end=np.array(end,float);da=unit(da);db=unit(db);straight=3 if r<1 else 5
 a=start+da*straight;b=end+db*straight;h=np.array([a]+[np.array(x) for x in hints]+[b]);dist=np.r_[0,np.cumsum(np.linalg.norm(np.diff(h,axis=0),axis=1))]
 n=min(16,max(4,len(hints)+1));scale=max(5,dist[-1]/(n+1));u=np.linspace(0,n+1,(n+1)*16+1)
 q=np.linspace(0,dist[-1],n+2)[1:-1];seed=np.stack([np.interp(q,dist,h[:,j]) for j in range(3)],axis=1)
 def curve(x):return CubicSpline(np.arange(n+2),np.vstack([a,x[:3*n].reshape(n,3),b]),bc_type=((1,da*np.exp(x[-2])),(1,-db*np.exp(x[-1]))))
 def residual(x,detail=False):
  c=curve(x);pt=c(u);vel=c(u,1);acc=c(u,2);spd=np.linalg.norm(vel,axis=1);curv=np.linalg.norm(np.cross(vel,acc),axis=1)/np.maximum(spd**3,1e-12)
  bd=body_dist(pt)-r-.15;near=np.minimum(np.linalg.norm(pt-start,axis=1),np.linalg.norm(pt-end,axis=1));bd[near<r+.6,:]=np.maximum(bd[near<r+.6,:],0)
  hd=head_dist(pt)-r-.8;segments=np.linalg.norm(np.diff(pt,axis=0),axis=1);length=segments.sum()+2*straight
  # Keep the route in a narrow neighborhood of its intended structural corridor.
  nodes=x[:3*n].reshape(n,3);guide=(nodes-seed)
  out=[np.maximum(-bd,0).ravel()*100,np.maximum(-hd,0)*100,np.maximum(curv*minr*margin-1,0)*220,np.maximum(1-spd,0)*30,guide.ravel()*.16,segments*.06,acc.ravel()*.005]
  if K=='A' and 'POWER' not in name and 'FACTORY' not in name:
   out += [np.maximum(pt[:,2]+r-66,0)*30,np.maximum(abs(pt[:,0])+r-109,0)*20,np.maximum(pt[:,1]-(design['camera_center'][1]+6),0)*100]
  if target:out.append(np.array([(length-target)*2]))
  if detail:return dict(body_violation_mm=float(max(0,-bd.min())),head_violation_mm=float(max(0,-hd.min())),sample_min_radius_mm=float(1/max(curv.max(),1e-12)),length_mm=float(length))
  return np.concatenate(out)
 low=np.r_[np.tile([-137,-145,-30],n),np.log([2,2])];high=np.r_[np.tile([137,design['camera_center'][1]+7,150],n),np.log([120,120])]
 best=None
 for i,offset in enumerate([(0,0,0),(3,0,6),(-4,0,10)]):
  x0=np.r_[(seed+offset).ravel(),np.log([scale,scale])]
  if best is not None and best[0]<.3:x0=best[1]
  opt=least_squares(residual,np.clip(x0,low+.001,high-.001),bounds=(low,high),max_nfev=95,ftol=3e-6,xtol=3e-6,diff_step=1e-4)
  d=residual(opt.x,True);score=max(d['body_violation_mm'],d['head_violation_mm'],(minr-d['sample_min_radius_mm'])*5)
  if best is None or score<best[0]:best=(score,opt.x,d)
  if score<.035:break
 c=curve(best[1]);segs=[line(start,a)]
 for i in range(n+1):segs.append(np.array([c(i),c(i)+c(i,1)/3,c(i+1)-c(i+1,1)/3,c(i+1)]))
 segs.append(line(b,end));segs=np.array(segs);d=metrics(segs);d.update(best[2]);d['min_radius_mm']=metrics(segs)['min_radius_mm']
 print(name,'R',round(d['min_radius_mm'],3),'target',minr,'body',round(d['body_violation_mm'],3),'head',round(d['head_violation_mm'],3),'L',round(d['length_mm'],1),flush=True)
 return segs,d
def endpoint(n):return np.array(L[n]['point']),np.array(L[n]['direction'])
def add(name,a,b,r=.4,minr=3.2,hints=[],target=None,net=None):
 start,da=endpoint(a);end,db=endpoint(b);segs,m=solve(name,start,end,da,db,r,minr,hints,target,1.4 if ('IMU' in name or name=='USB_Camera') else 1.18)
 results[name]=dict(a=a,b=b,radius_mm=r,criterion_radius_mm=minr,net=net or name,segments=segs.tolist(),metrics=m)
 (D/'routes.json').write_text(json.dumps(results,indent=2),encoding='utf-8')

names=sys.argv[2:]
if names and (D/'routes.json').exists():results=json.loads((D/'routes.json').read_text())
def wanted(n):return not names or n in names
mainz=endpoint('LEAD__R1')[0][2];cx,cy,cz=design['camera_center'];rightx=endpoint('LEAD__R1')[0][0]-7
for pin,label in [(17,'VDD'),(9,'GND'),(14,'LR'),(38,'SD'),(12,'SCK'),(35,'WS')]:
 name='MIC_'+label
 if not wanted(name):continue
 a=endpoint('LEAD__R'+str(pin))[0];b=endpoint('LEAD__MIC_'+label)[0];h=[[rightx,a[1],mainz+7],[rightx,(a[1]+b[1])/2,mainz+8],[b[0],b[1],b[2]+7]]
 add(name,'LEAD__R'+str(pin),'LEAD__MIC_'+label,hints=h,net='I2S12' if pin==12 else 'I2S35' if pin==35 else None)
for pin,label in [(2,'VIN'),(20,'GND'),(40,'DIN'),(12,'BCLK'),(35,'LRC')]:
 name='AMP_'+label
 if not wanted(name):continue
 a=endpoint('LEAD__R'+str(pin))[0];b=endpoint('LEAD__AMP_'+label)[0];h=[[rightx,a[1],mainz+7],[rightx,b[1]+14,max(mainz+6,b[2]+5)]]
 add(name,'LEAD__R'+str(pin),'LEAD__AMP_'+label,hints=h,net='I2S12' if pin==12 else 'I2S35' if pin==35 else None)
for i,pin in enumerate([1,6,27,28]):
 name='IMU_'+str(pin)
 if not wanted(name):continue
 a=endpoint('LEAD__R'+str(pin))[0];b=endpoint('QWIRE_END_'+str(i))[0]
 h=[[rightx,a[1],mainz+8],[rightx,48,mainz+10],[75,cy-35,cz+19],[b[0]+9,b[1],b[2]]]
 add(name,'LEAD__R'+str(pin),'QWIRE_END_'+str(i),hints=h)
if wanted('USB_Data'):
 a=endpoint('LEAD__Radxa_HOST')[0];b=endpoint('LEAD__Splitter_DATA')[0];x=max(a[0]+10,b[0]+18)
 add('USB_Data','LEAD__Radxa_HOST','LEAD__Splitter_DATA',1.5,12,[[x,a[1]-23,a[2]+15],[x,a[1]-5,a[2]+29],[x,b[1]-35,b[2]+12],[b[0],b[1],b[2]+16]])
if wanted('USB_Camera'):
 a=endpoint('LEAD__CS30_USB')[0];b=endpoint('LEAD__Splitter_OUT')[0]
 add('USB_Camera','LEAD__CS30_USB','LEAD__Splitter_OUT',1.5,12,[[a[0],cy-30,a[2]+5],[-28,cy-30,cz+10],[14,cy-29,cz+10],[b[0],b[1],b[2]+16]])
for i,label in enumerate(['PLUS','MINUS']):
 name='SPEAKER_FACTORY_'+label
 if wanted(name):
  h=[[-102-i*1.5,10,24],[-105-i*1.5,-24,39],[-104-i*1.5,-54,32],[-90-i*1.5,-54,28]]
  add(name,'SPEAKER_'+label,'PH125_IN_'+label,.55,4.4,h,target=120)
 name='SPEAKER_LINK_'+label
 if wanted(name):
  a=endpoint('AMP_OUTPUT_'+label)[0];b=endpoint('PH125_OUT_'+label)[0];zz=max(mainz+8,a[2]+8);fz=cz+20
  h=[[a[0]-5,a[1]-14,a[2]],[rightx+8,-58,zz],[rightx+5,10,zz],[86,45,fz],[64,cy-45,fz],[30,cy-26,fz+i*1.4],[-28,cy-26,fz+i*1.4],[-68,cy-42,cz+12],[-85,35,max(48,cz-15)],[-88,-28,46],[-86,-61,35],[-84,-58,9],[b[0],b[1],b[2]-9]]
  add(name,'AMP_OUTPUT_'+label,'PH125_OUT_'+label,.55,4.4,h)

def quarter(center,u,v,r,t0,t1):
 d=t1-t0;k=4/3*math.tan(d/4);a=center+r*(math.cos(t0)*u+math.sin(t0)*v);b=center+r*(math.cos(t1)*u+math.sin(t1)*v)
 ta=-math.sin(t0)*u+math.cos(t0)*v;tb=-math.sin(t1)*u+math.cos(t1)*v
 return np.array([a,a+k*r*ta,b-k*r*tb,b])
def service_curve(a,u,v,r,straight=0):
 # Two opposed semicircles. Horizontal runs at their peaks make the loop extensible without tightening its bend.
 segs=[];c=a+u*r
 segs.append(quarter(c,u,v,r,math.pi,math.pi/2));top=segs[-1][-1]
 if straight>0:segs.append(line(top,top+u*straight))
 c+=u*straight;segs.append(quarter(c,u,v,r,math.pi/2,0));end=segs[-1][-1];c=end+u*r
 segs.append(quarter(c,u,v,r,math.pi,3*math.pi/2));bot=segs[-1][-1]
 if straight>0:segs.append(line(bot,bot+u*straight))
 c+=u*straight;segs.append(quarter(c,u,v,r,3*math.pi/2,2*math.pi));return np.array(segs)
for i,dest in enumerate(['LEAD__Radxa_OTG','LEAD__Splitter_POWER']):
 name='POWER_'+str(i+1)
 if not wanted(name):continue
 source='LEAD__Battery_C'+('_2' if i else '');a,da=endpoint(source);b,db=endpoint(dest)
 v=np.array([0.,0.,1.]);xdir=np.array([1.,0.,0.]);p=a+da*5
 first=quarter(p+xdir*14,-xdir,da,14,0,math.pi/2);p2=first[-1]
 second=quarter(p2+v*14,-v,xdir,14,0,math.pi/2)
 prefix=np.array([line(a,p),first,second]);A=prefix[-1][-1];u=unit([35,math.sqrt(88**2-35**2),0]);B=A+u*88
 pts=sample(prefix);pm=metrics(prefix);pm.update(body_violation_mm=0.,head_violation_mm=float(max(0, -(head_dist(pts)-2.3).min())))
 mid=service_curve(A,u,v,22);x=max(105,b[0]+10)
 tail,tm=solve(name+'_mirror',B,b,v,db,1.5,12,[[x,B[1],B[2]+18],[x,b[1]-20,max(18,b[2]+15)],[b[0]+db[0]*16,b[1]+db[1]*16,b[2]+db[2]*16]],margin=1.3)
 segs=np.concatenate([prefix,mid,tail]);m=metrics(segs);m.update(body_violation_mm=max(pm['body_violation_mm'],tm['body_violation_mm']),head_violation_mm=max(pm['head_violation_mm'],tm['head_violation_mm']))
 sl=metrics(mid)['length_mm'];extended=88+20;newr=(sl-extended)/(2*math.pi-4);straight=(extended-4*newr)/2;stretched=service_curve(A,u,v,newr,straight);stretchmet=metrics(stretched)
 results[name]=dict(a=source,b=dest,radius_mm=1.5,criterion_radius_mm=12.,net=name,segments=segs.tolist(),metrics=m,clamps=[A.tolist(),B.tolist()],clamp_axis=v.tolist(),service_segment_range=[len(prefix),len(prefix)+len(mid)],service_loop=dict(initial_chord_mm=88.,initial_length_mm=sl,stretch_allowance_mm=20.,minimum_radius_at_full_extension_mm=stretchmet['min_radius_mm'],full_extension_length_mm=stretchmet['length_mm'],spare_over_chord_mm=sl-88,stretched_segments=stretched.tolist()))
 (D/'routes.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
print('ROUTING DONE',K,len(results),flush=True)
