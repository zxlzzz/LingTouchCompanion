"""One-piece open-backed video-prop visor, using the true customer camera.

Millimeters; wearing X lateral, Y posterior, Z up. No camera threads, rear
cover, precision snap, electronics clearance or camera operation is assumed.
"""
from pathlib import Path
import json, math, hashlib, sys
import numpy as np
import manifold3d as md

P=Path(__file__).resolve().parent
R=P.parent; I=R/'Headset_Inputs'; G=P/'geometry'; G.mkdir(exist_ok=True)
sys.path.insert(0,str(I))
from head_surface import HeadSurface
M=md.Manifold
WALL=1.4
FACE_HALF=70.
ARM_START_X=81.5
OVAL_CENTER_Z=41.
REAR_Y=5.712128
CAMERA_T=np.array([[1,0,0,-.0290536247],[0,0,-1,REAR_Y-25],[0,1,0,38.]])
DATUMS=json.loads((I/'datums.json').read_text(encoding='utf-8-sig'))

def box(lo,hi):
    lo=np.array(lo); return M.cube(tuple(np.array(hi)-lo)).translate(tuple(lo))
def union(ms): return M.batch_boolean(ms,md.OpType.Add)
def mesh(v,f):
    v=np.ascontiguousarray(v,dtype=np.float64); f=np.ascontiguousarray(f,dtype=np.uint64)
    tri=v[f]; signed=np.einsum('ij,ij->i',tri[:,0],np.cross(tri[:,1],tri[:,2])).sum()
    if signed<0: f=f[:,::-1].copy()
    result=M(md.Mesh64(vert_properties=v,tri_verts=f))
    assert result.status()==md.Error.NoError,result.status()
    return result
def save(name,m,material=None):
    assert m.status()==md.Error.NoError,(name,m.status())
    a=m.to_mesh64(); v=np.asarray(a.vert_properties)[:,:3];f=np.asarray(a.tri_verts)
    kw={'v':v,'f':f}
    if material is not None: kw['material']=material(v,f)
    np.savez_compressed(G/(name+'.npz'),**kw)
    return {'volume_cm3':float(m.volume())/1000,'components':len(m.decompose()),
            'vertices':len(v),'faces':len(f),'bounds_xyz_mm':[v.min(0).tolist(),v.max(0).tolist()]}
def smooth(t):
    t=np.clip(t,0,1);return t*t*t*(10-15*t+6*t*t)
def dimensions(x):
    q=abs(x)
    front=-23.8+2.4*(min(q,46)/46)**2
    if q>46:front+=.5*smooth((q-46)/24)
    return front,6.8,23.4+1.6*(q/70)**2,68.4-3.6*(q/70)**2
def front_y(x): return dimensions(x)[0]
def profile(x,inside=False):
    front,back,low,top=dimensions(x)
    if inside:
        h=.005
        derivatives=(np.array(dimensions(x+h))-np.array(dimensions(x-h)))/(2*h)
        offsets=WALL*np.sqrt(1+derivatives**2)
        front+=offsets[0];back-=offsets[1];low+=offsets[2];top-=offsets[3]
    depth=back-front; height=top-low
    assert depth>0 and height>0,(x,depth,height)
    maxr=min(depth,height)/2-.02
    rt=min(8-(WALL if inside else 0),maxr)
    rb=min(3.5-(WALL if inside else 0),maxr)
    rr=max(.35,min(2-WALL if inside else 2,maxr))
    pts=[]
    for (y,z),radius,(a,b) in zip([(front+rb,low+rb),(back-rr,low+rr),(back-rr,top-rr),(front+rt,top-rt)],
                                 [rb,rr,rr,rt],[(math.pi,1.5*math.pi),(1.5*math.pi,2*math.pi),(0,.5*math.pi),(.5*math.pi,math.pi)]):
        for angle in np.linspace(a,b,17):pts.append([x,y+radius*math.cos(angle),z+radius*math.sin(angle)])
    return pts

def section(width,height,radii):
    pts=[];front=-width/2;back=width/2;low=-height/2;top=height/2
    rf,rr,rt,rfl=radii
    for (y,z),radius,(a,b) in zip([(front+rfl,low+rfl),(back+0-rr,low+rr),(back-rt,top-rt),(front+rf,top-rf)],
                                  [rfl,rr,rt,rf],[(math.pi,1.5*math.pi),(1.5*math.pi,2*math.pi),(0,.5*math.pi),(.5*math.pi,math.pi)]):
        for t in np.linspace(a,b,17):pts.append([y+radius*math.cos(t),z+radius*math.sin(t)])
    return np.array(pts)

def shoulder(t,side,inside=False):
    # A quarter turn with a continuous tangent replaces the old intersecting
    # vertical end cap / larger oval arm collar.
    u=t*math.pi/2;s=smooth(t);hs=smooth((t-.72)/.28)
    center=np.array([side*(70+11.5*math.sin(u)),-7.05+50.05*(1-math.cos(u)),44.9-3.9*hs])
    theta=math.atan2(50.05*math.sin(u),11.5*math.cos(u))
    width=27.7*(1-s)+4.4*s;height=39.8*(1-hs)+12*hs
    radii=[8*(1-s)+2.18*s,2*(1-s)+2.18*s,2*(1-s)+2.18*s,3.5*(1-s)+2.18*s]
    if inside:
        width-=2*WALL;height-=2*WALL;radii=[max(.2,r-WALL) for r in radii]
    radii=[min(r,width/2-.01,height/2-.01) for r in radii]
    local=section(width,height,radii)
    return [[center[0]-side*a*math.sin(theta),center[1]+a*math.cos(theta),center[2]+z] for a,z in local]

def arm_rows(side,head):
    keys=[43,60,80,95,110,125,140,150,159.0703299]
    heights=[12,12,12,12,13,17,28,32,32]
    widths=[4.4,3.6,3.4,3.4,3.4,3.4,3.4,3.3,3.3]
    centers=[41,40.5,40,40,40,39.8,39.2,39.2,39.2]
    tab=DATUMS['terminal_left_x' if side<0 else 'terminal_right_x'];terminal_x=abs(np.mean(tab))
    # Smooth conservative landmarks, rather than following each ear triangle.
    xguide=[]
    for i,(y,h,w,z,base) in enumerate(zip(keys,heights,widths,centers,[ARM_START_X,ARM_START_X,83,89,90,90,88,terminal_x,terminal_x])):
        # Sample the whole adjacent ear region before constructing one smooth
        # guide. Raw per-row clamping would imprint skin-mesh corrugation.
        ya=keys[max(0,i-1)];yb=keys[min(len(keys)-1,i+1)]
        skin=[abs(head.lateral_x(yy,zz,side)) for yy in np.linspace(ya,yb,25) for zz in np.linspace(23.2,55.2,25)]
        skin=[a for a in skin if np.isfinite(a)]
        xguide.append(max(base,max(skin)+w/2+.65) if skin and y<145 else base)
    rows=[]
    for y in np.linspace(43,DATUMS['terminal_reach_y'],234):
        h=cubic(keys,heights,y);w=cubic(keys,widths,y);z=cubic(keys,centers,y);x=cubic(keys,xguide,y)
        terminal=smooth((y-143)/7)
        w=w*(1-terminal)+(tab[1]-tab[0])*terminal
        r=min(w/2-.01,h/2-.01)
        # The same 68-point section topology continues from the shoulder.
        local=section(w,h,[r,r,r,r])
        rows.append([[side*x-side*a,y,z+b] for a,b in local])
    return rows
def loft(rows):
    rows=np.array(rows);n=len(rows[0]);v=rows.reshape(-1,3).tolist();f=[]
    for k in range(len(rows)-1):
        for j in range(n):
            a=k*n+j;b=k*n+(j+1)%n;c=(k+1)*n+(j+1)%n;d=(k+1)*n+j
            f.extend([[a,b,c],[a,c,d]])
    for k in (0,len(rows)-1):
        c=len(v);v.append(rows[k].mean(0).tolist())
        for j in range(n):f.append([c,k*n+(j+1)%n,k*n+j] if k==0 else [c,k*n+j,k*n+(j+1)%n])
    return mesh(v,f)
def rounded(w,h,r,center=(0,0)):
    pts=[]
    for x,z,a in [(w/2-r,h/2-r,0),(-w/2+r,h/2-r,90),(-w/2+r,-h/2+r,180),(w/2-r,-h/2+r,270)]:
        for t in np.linspace(math.radians(a),math.radians(a+90),25):
            pts.append([center[0]+x+r*math.cos(t),center[1]+z+r*math.sin(t)])
    return md.CrossSection([np.array(pts)])
def xz_prism(cs,ymin,ymax):
    return cs.extrude(ymax-ymin).transform([[1,0,0,0],[0,0,-1,ymax],[0,1,0,0]])
def cylinder_y(x,z,ymin,ymax,r):
    return M.cylinder(ymax-ymin,r,r,96).transform([[1,0,0,x],[0,0,-1,ymax],[0,1,0,z]])

def skin_cutter(head,clearance=.12,xs=None,zs=None):
    # Only the visor is trimmed by this front skin sheet. The arms follow the
    # separate lateral surface; cutting them with a front half-space is wrong.
    if xs is None:xs=np.linspace(-96,96,385)
    if zs is None:zs=np.linspace(15,72,115)
    ys=head.front_grid(xs,zs,missing=200)-clearance
    nx,nz=ys.shape;v=[]
    for back in (False,True):
        for i,x in enumerate(xs):
            for j,z in enumerate(zs):v.append([x,200 if back else ys[i,j],z])
    size=nx*nz;f=[]
    for i in range(nx-1):
        for j in range(nz-1):
            a=i*nz+j;b=(i+1)*nz+j;c=b+1;d=a+1
            f.extend([[a,b,c],[a,c,d],[a+size,c+size,b+size],[a+size,d+size,c+size]])
    boundary=[i*nz for i in range(nx)]+[(nx-1)*nz+j for j in range(1,nz)]+[i*nz+nz-1 for i in range(nx-2,-1,-1)]+[j for j in range(nz-2,0,-1)]
    for a,b in zip(boundary,boundary[1:]+boundary[:1]):f.extend([[a,a+size,b+size],[a,b+size,b]])
    return mesh(v,f)

def lateral_skin_cutter(head):
    ys=np.linspace(43,165,245);zs=np.linspace(15,72,115)
    left=head.lateral_grid(ys,zs,-1,missing=0)-.12
    right=head.lateral_grid(ys,zs,1,missing=0)+.12
    ny,nz=left.shape;size=ny*nz;v=[];f=[]
    for surface in (left,right):
        for i,y in enumerate(ys):
            for j,z in enumerate(zs):v.append([surface[i,j],y,z])
    for i in range(ny-1):
        for j in range(nz-1):
            a=i*nz+j;b=(i+1)*nz+j;c=b+1;d=a+1
            f.extend([[a,c,b],[a,d,c],[a+size,b+size,c+size],[a+size,c+size,d+size]])
    boundary=[i*nz for i in range(ny)]+[(ny-1)*nz+j for j in range(1,nz)]+[i*nz+nz-1 for i in range(ny-2,-1,-1)]+[j for j in range(nz-2,0,-1)]
    for a,b in zip(boundary,boundary[1:]+boundary[:1]):f.extend([[a,b,b+size],[a,b+size,a+size]])
    return mesh(v,f)

def cubic(keys,values,y):
    # Smooth Hermite interpolation gives a continuous arm, including the
    # enlarged strap terminal; no separately joined thin BTTF plate.
    k=np.asarray(keys);p=np.asarray(values)
    i=min(len(k)-2,max(0,np.searchsorted(k,y)-1));t=(y-k[i])/(k[i+1]-k[i])
    slopes=np.empty_like(p,dtype=float)
    slopes[1:-1]=(p[2:]-p[:-2])/(k[2:]-k[:-2]);slopes[0]=0;slopes[-1]=0
    for j in np.flatnonzero(np.isclose(np.diff(p),0,atol=1e-10)):
        slopes[j]=slopes[j+1]=0
    d=k[i+1]-k[i]
    return (2*t**3-3*t*t+1)*p[i]+(t**3-2*t*t+t)*d*slopes[i]+(-2*t**3+3*t*t)*p[i+1]+(t**3-t*t)*d*slopes[i+1]
def paint(v,f):
    c=v[f].mean(1);dx=np.maximum(abs(c[:,0])-31,0)
    radial=np.sqrt(dx*dx+(c[:,2]-OVAL_CENTER_Z)**2)
    return ((radial>=12.95)&(radial<=14.05)&(c[:,1]<np.array([front_y(x) for x in c[:,0]])+.35)).astype(np.uint8)

def build():
    head=HeadSurface()
    print('Building sculpted hollow visor and continuous arms',flush=True)
    mid=[profile(x) for x in np.linspace(-70,70,281)]
    left=[shoulder(t,-1) for t in np.linspace(1,0,81)[:-1]]
    right=[shoulder(t,1) for t in np.linspace(0,1,81)[1:]]
    larm=arm_rows(-1,head)[::-1][:-1]
    outer=loft(larm+left+mid+right+arm_rows(1,head)[1:])
    il=[shoulder(t,-1,True) for t in np.linspace(1,0,81)[:-1]]
    inner=loft(il+[profile(x,True) for x in np.linspace(-70,70,281)]+[shoulder(t,1,True) for t in np.linspace(0,1,81)[1:]])
    front_skin=skin_cutter(head)
    hood=outer-inner-(front_skin^box([-100,-100,0],[100,43,100]))-lateral_skin_cutter(head)
    # Explicit face-side opening removes every rear wall patch. Top, bottom
    # and end walls remain around the camera; no rear cover exists.
    hood-=xz_prism(rounded(143.5,41.2,1.0,(0,45.4)),REAR_Y-.8,100)
    # Thin cheek returns reach the true skin boundary, hiding the camera from
    # rear-side views while leaving the central face side entirely open.
    # Compensate 0.25 mm surface interpolation by 0.02 mm at the plastic
    # contact edges. The camera itself retains exact forehead contact.
    contact_skin=skin_cutter(head,.02,np.linspace(-48,48,385),np.linspace(24,60,145))
    returns=[]
    for side in (-1,1):
        returns.append(xz_prism(rounded(1.4,32.5,.68,(side*46.95,41.05)),-1,45)-contact_skin)
    # A thin inner ceiling closes upward sightlines at the skin boundary.
    # Its open rear edge is not a rear cover; camera rear contact is retained.
    ceiling_rows=[]
    for x in np.linspace(-47,47,189):
        y=front_y(x)+.8
        ceiling_rows.append([[x,y,57],[x,45,57],[x,45,58.2],[x,y,58.2]])
    ceiling=loft(ceiling_rows)-contact_skin
    hood=union([hood,*returns,ceiling])
    # Broad generic seating stops contact the real front/bottom, without a
    # fitted cavity or hooks. Adjustable webbing supplies the clamping force.
    stops=[]
    for x in (-35,35):
        stops.append(box([x-3,front_y(x)+.8,34],[x+3,REAR_Y-25,42]))
    for x in (-22,22):
        stops.append(box([x-4,REAR_Y-18,23.5],[x+4,REAR_Y-13,25.5]))
    hood=union([hood,*stops])
    # Sidewall strap eyes lie outside the real camera ends. Opaque tunnels
    # face the rear opening and do not pierce the visible lateral skin.
    for side in (-1,1):
        x=side*50;y=REAR_Y-3.5
        ear=box([x-3.3,y-3.2,26.25],[x+3.3,y+3.2,46.75])^outer
        ear-=box([x-4.3,y-1.1,28.25],[x+4.3,y+1.1,44.75])
        hood+=ear
    # Continue the textile passage through the internal cheek returns.
    # The exterior wing remains opaque around this inward-facing tunnel.
    for side in (-1,1):
        x=side*50;y=REAR_Y-3.5
        hood-=box([x-4.3,y-1.1,28.25],[x+4.3,y+1.1,44.75])
    body=hood
    # Preserve the previous terminal slot XYZ and longitudinal reach exactly.
    for side in (-1,1):
        tab=DATUMS['terminal_left_x' if side<0 else 'terminal_right_x']
        y0,y1=DATUMS['terminal_slot_y'];z0,z1=DATUMS['terminal_slot_z']
        body-=box([tab[0]-5,y0,z0],[tab[1]+5,y1,z1])
    # Real shallow integral paint groove; a solid opaque panel remains behind
    # the long oval. Only the three real optical apertures pass through it.
    oval=rounded(90,28,14,(0,OVAL_CENTER_Z)); ring=oval-oval.offset(-1,circular_segments=96)
    slab_rows=[]
    for x in np.linspace(-46,46,185):
        fy=front_y(x);slab_rows.append([[x,fy-5,25],[x,fy+.28,25],[x,fy+.28,57],[x,fy-5,57]])
    groove=xz_prism(ring,-40,0)^loft(slab_rows)
    body-=groove
    optics=[{'name':'RGB','x':-22-.0290536247,'z':38,'opening_mm':[15.5,15.5],'radial_allowance_mm':1.5},
            {'name':'TX','x':7-.0290536247,'z':38,'opening_mm':[9,6.5],'edge_allowance_mm':1},
            {'name':'RX','x':22-.0290536247,'z':38,'opening_mm':[16.5,16.5],'radial_allowance_mm':1.5}]
    cuts=[cylinder_y(o['x'],38,-40,20,o['opening_mm'][0]/2) if o['name']!='TX' else xz_prism(rounded(9,6.5,1,(o['x'],38)),-40,20) for o in optics]
    body-=union(cuts)
    # Render-only reference of the single 15 mm adjustable textile band. It is
    # not part of the printed body; return tail is supplied by the bought strap.
    path=np.array([[-54.5,REAR_Y-3.5],[-46,REAR_Y-3.5],[-45.5,REAR_Y+.35],[45.5,REAR_Y+.35],[46,REAR_Y-3.5],[54.5,REAR_Y-3.5]])
    lower=path.copy();upper=path.copy();lower[:,1]-=.35;upper[:,1]+=.35
    band=md.CrossSection([np.vstack([lower,upper[::-1]])]).extrude(15).translate((0,0,29))
    geometry={'front_body':save('front_body',body,paint),'retention_band':save('retention_band',band)}
    for name,src in [('camera','camera_physical_native.npz'),('camera_optics','camera_optics_native.npz')]:
        a=np.load(P/'inputs'/src);v=np.asarray(a['v'])@CAMERA_T[:,:3].T+CAMERA_T[:,3]
        out={k:a[k] for k in a.files};out['v']=v
        np.savez_compressed(G/(name+'.npz'),**out)
    a=np.load(R/'Headset_Rear/geometry/straps.npz');v=a['v'].copy()
    front=v[:,1]<160;v[front,0]+=np.sign(v[front,0])*5.1
    np.savez_compressed(G/'connection_straps.npz',v=v,f=a['f'])
    values={'camera_transform_native_to_wearing':CAMERA_T.tolist(),'camera_orientation':'Level forward, actual bottom down, optical centers Z38 mm; unpowered prop.',
            'camera_rear_y_mm':REAR_Y,'camera_bottom_z_mm':25.49995,'shell_wall_mm':WALL,
            'optics':optics,'geometry':geometry,'head_audit_parts':['front_body','camera','retention_band'],
            'nominal_clearance_mm':{'front_center':3.112128,'front_at_camera_ends':1.0,'camera_ceiling':1.5,'camera_end_to_cheek':1.28,'bottom_seat':0,'rear_to_skin':0},
            'internal_ceiling_mm':{'underside_z':57,'thickness':1.2,'width':94,'rear_edge':'Nominal contact with registered head surface; face side remains open.'},
            'front_design_dimensions_mm':{'broad_frontal_width':140,'central_height':45,'integral_long_oval':[90,28],'oval_center_z':OVAL_CENTER_Z,'groove_width':1,'groove_depth':.28},
            'rear_opening_mm':{'width':143.5,'height':41.2,'center_z':45.4,'front_y':REAR_Y-.8},
            'fixing':'One 15 mm hook-loop cinch band; 40 mm parallel folded overlap; generic broad front/floor stops. No camera hole, rear cover or fitted snap.',
            'retention_band_mm':{'width':15,'suggested_purchase_length':220,'folded_overlap_min':40,'reference_thickness':.7,'eyes':[2.2,16.5]},
            'unchanged_slots_y_mm':DATUMS['terminal_slot_y'],'unchanged_slots_z_mm':DATUMS['terminal_slot_z'],
            'unchanged_reach_y_mm':DATUMS['terminal_reach_y'],'source_hashes':{str(p.relative_to(R)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in [I/'CS30_customer.stp',I/'BTTF_Glasses.3mf',I/'Medium_Trial_Registered.npz',I/'datums.json',P/'inputs/camera_physical_native.npz']}}
    (G/'geometry_values.json').write_text(json.dumps(values,indent=2),encoding='utf8')
    print(json.dumps(geometry,indent=2),flush=True)
    assert geometry['front_body']['components']==1,'Visor and arms must be one connected piece'

if __name__=='__main__':build()
