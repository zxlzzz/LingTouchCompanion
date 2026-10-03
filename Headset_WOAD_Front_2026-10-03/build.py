"""Rounded WOAD-inspired front shell. All dimensions are mm in wearing coordinates.

The raw BTTF Normal temples keep their original Y/Z and length. The rear
assembly is read only. Physical camera triangles are the customer STEP,
not a box; its optical simulation cones have been excluded.
"""
from pathlib import Path
import json, math, hashlib, zipfile
import xml.etree.ElementTree as ET
import numpy as np
import manifold3d as md

P=Path(__file__).resolve().parent
R=P.parent
G=P/'geometry';G.mkdir(exist_ok=True)
M=md.Manifold
WALL=2.4
CAMERA_T=np.array([[1,0,0,-.0290536247],[0,0,-1,-30.0],[0,1,0,35.5]])
def box(lo,hi):
    lo=np.array(lo);return M.cube(tuple(np.array(hi)-lo)).translate(tuple(lo))
def union(ms):return M.batch_boolean(ms,md.OpType.Add)
def load(path):
    q=np.load(path);return M(md.Mesh64(vert_properties=np.ascontiguousarray(q['v'],dtype=np.float64),tri_verts=np.ascontiguousarray(q['f'],dtype=np.uint64)))
def save(name,m):
    assert m.status()==md.Error.NoError,(name,m.status())
    a=m.to_mesh64();v=np.asarray(a.vert_properties)[:,:3];f=np.asarray(a.tri_verts)
    np.savez_compressed(G/(name+'.npz'),v=v,f=f)
    return {'volume_cm3':float(m.volume())/1000,'components':len(m.decompose()),'vertices':len(v),'faces':len(f),'bounds_xyz_mm':[v.min(0).tolist(),v.max(0).tolist()] if len(v) else None}
def mesh(v,f):
    v=np.asarray(v,dtype=np.float64);f=np.asarray(f,dtype=np.uint64)
    tri=v[f];vol=np.einsum('ij,ij->i',tri[:,0],np.cross(tri[:,1],tri[:,2])).sum()
    if vol<0:f=f[:,::-1].copy()
    m=M(md.Mesh64(vert_properties=np.ascontiguousarray(v),tri_verts=np.ascontiguousarray(f)))
    assert m.status()==md.Error.NoError,m.status()
    return m
def smooth01(t):
    t=np.clip(t,0,1);return t*t*t*(10-15*t+6*t*t)
def profile(x,inside=False):
    q=abs(x)
    front=-34.4+66.4*smooth01((q-43)/29)
    back=.4+43.6*smooth01((q-50)/22)
    # Keep a continuous, positive inner section through the visor-to-temple turn.
    # The smooth positive-part avoids both an inverted hollow contour and a crease.
    d=back-front-12
    extra=0 if d<=-2 else (d if d>=2 else (d+2)**2/8)
    front=back-(12+extra)
    low=5+14*math.exp(-(x/15)**2)
    top=58-3*smooth01((q-48)/24)
    if inside:front+=WALL;back-=WALL;low+=WALL;top-=WALL
    rf=min(7 if not inside else 4.6,(back-front)/2-.03,(top-low)/2-.03)
    rfl=min(5 if not inside else 2.6,(back-front)/2-.03,(top-low)/2-.03)
    rb=min(2.5 if not inside else .5,(back-front)/2-.03,(top-low)/2-.03)
    rr=[rfl,rb,rb,rf]
    centers=[(front+rfl,low+rfl),(back-rb,low+rb),(back-rb,top-rb),(front+rf,top-rf)]
    ranges=[(math.pi,1.5*math.pi),(1.5*math.pi,2*math.pi),(0,.5*math.pi),(.5*math.pi,math.pi)]
    pts=[]
    for (y,z),radius,(a,b) in zip(centers,rr,ranges):
        for t in np.linspace(a,b,19):pts.append([x,y+radius*math.cos(t),z+radius*math.sin(t)])
    return pts
def loft_profiles(xs,inside=False):
    rows=np.array([profile(x,inside) for x in xs]);n=len(rows[0]);v=rows.reshape(-1,3).tolist();f=[]
    for k in range(len(rows)-1):
        for j in range(n):
            a=k*n+j;b=k*n+(j+1)%n;c=(k+1)*n+(j+1)%n;d=(k+1)*n+j
            f.extend([[a,b,c],[a,c,d]])
    for k in [0,len(rows)-1]:
        c=len(v);v.append(rows[k].mean(0).tolist())
        for j in range(n):f.append([c,k*n+(j+1)%n,k*n+j] if k==0 else [c,k*n+j,k*n+(j+1)%n])
    return mesh(v,f)
def rounded_section(w,h,r,center=(0,0)):
    pts=[]
    for x,z,a in [(w/2-r,h/2-r,0),(-w/2+r,h/2-r,90),(-w/2+r,-h/2+r,180),(w/2-r,-h/2+r,270)]:
        for t in np.linspace(math.radians(a),math.radians(a+90),25):pts.append([center[0]+x+r*math.cos(t),center[1]+z+r*math.sin(t)])
    return md.CrossSection([np.array(pts)])
def xz_prism(cs,ymin,ymax):
    # The orientation-preserving transform sends local +extrusion towards -Y.
    return cs.extrude(ymax-ymin).transform([[1,0,0,0],[0,0,-1,ymax],[0,1,0,0]])
def cylinder_y(x,z,ylo,yhi,r):
    return M.cylinder(yhi-ylo,r,r,64).transform([[1,0,0,x],[0,0,-1,yhi],[0,1,0,z]])
def raw_normal():
    core='{http://schemas.microsoft.com/3dmanufacturing/core/2015/02}'
    prod='{http://schemas.microsoft.com/3dmanufacturing/production/2015/06}'
    with zipfile.ZipFile(R/'Headset_Repro/raw/BTTF_Glasses.3mf') as ar:
        models={n:ET.fromstring(ar.read(n)) for n in ar.namelist() if n.endswith('.model')}
        def flatten(name,oid):
            ob=next(o for o in models[name].findall(core+'resources/'+core+'object') if o.get('id')==oid)
            me=ob.find(core+'mesh')
            if me is not None:
                v=np.array([[float(n.get(a)) for a in 'xyz'] for n in me.findall(core+'vertices/'+core+'vertex')]);f=np.array([[int(n.get(a)) for a in ['v1','v2','v3']] for n in me.findall(core+'triangles/'+core+'triangle')]);return v,f
            vv=[];ff=[];off=0
            for c in ob.findall(core+'components/'+core+'component'):
                v,f=flatten(c.get(prod+'path',name).lstrip('/'),c.get('objectid'))
                if c.get('transform'):
                    t=np.array([float(a) for a in c.get('transform').split()]).reshape(4,3);v=v@t[:3]+t[3]
                vv.append(v);ff.append(f+off);off+=len(v)
            return np.concatenate(vv),np.concatenate(ff)
        root=models['3D/3dmodel.model'];item=next(q for q in root.findall(core+'build/'+core+'item') if q.get('objectid')=='2')
        v,f=flatten('3D/3dmodel.model','2');t=np.array([float(x) for x in item.get('transform').split()]).reshape(4,3)
        v=(v-(v.min(0)+v.max(0))/2)*np.linalg.norm(t[:3],axis=1)
        v += [0,73.53516495,27.587837475]
        return mesh(v,f)

def build():
    original=raw_normal()
    outer=loft_profiles(np.linspace(-72,72,289))
    inner=loft_profiles(np.linspace(-69.6,69.6,279),True)
    visor=outer-inner
    # Flat, removable rear closure; roof and nose floor stay continuous.
    opening_cs=rounded_section(96,33.6,5,(0,38.4))
    lid_cs=rounded_section(102,37,6,(0,38.4))
    opening=xz_prism(opening_cs,-15,80)
    recess=xz_prism(lid_cs.offset(.25,circular_segments=96),-1.85,80)
    visor=visor-opening-recess
    # A full rebate behind the service seam carries the cover and blocks views
    # through its fitting clearance. This is a structural 3.15 mm overlap lip.
    service_lip=xz_prism(lid_cs.offset(.25,circular_segments=96)-opening_cs,-5.0,-1.85)
    # Give the side USB plug a 0.5 mm allowance without cutting the exterior
    # wall or cover. The remaining 1.15 mm rebate still covers the seam.
    service_lip-=box([-52.5,-14,31],[-38.5,-3,40])
    visor+=service_lip
    lid=xz_prism(lid_cs,-1.6,.4)
    # Four M3 through-bolts into standard captive nuts, not camera threads.
    screws=[(-48,25),(48,25),(-48,51.8),(48,51.8)]
    bosses=[];bolt_cuts=[];nuts=[];bolts=[]
    for x,z in screws:
        boss=cylinder_y(x,z,-12,-1.85,3.8)
        # 5.9 mm across-flats hex seat for nominal 5.5 mm M3 nut.
        radius=5.9/math.sqrt(3)
        a=np.linspace(0,2*math.pi,7)[:-1]
        cs=md.CrossSection([np.column_stack([x+radius*np.cos(a),z+radius*np.sin(a)])])
        pocket=xz_prism(cs,-10.4,-7.8)
        access=xz_prism(cs,-13,-10.35)
        cut=cylinder_y(x,z,-13,3,1.7)
        bosses.append(boss-pocket-access-cut)
        bolt_cuts.append(cut)
        nut=xz_prism(md.CrossSection([np.column_stack([x+(5.5/math.sqrt(3))*np.cos(a),z+(5.5/math.sqrt(3))*np.sin(a)])]),-10.2,-7.8)-cylinder_y(x,z,-11,-7,1.5)
        nuts.append(nut)
        bolts.append(cylinder_y(x,z,-11.6,.4,1.5)+cylinder_y(x,z,.4,2.1,2.8))
    visor=union([visor,*bosses])-union(bolt_cuts)
    lid-=union(bolt_cuts)
    # Long-oval cosmetic recess: opaque shell behind it, three separate inner ports.
    bezel=rounded_section(74,30,15,(0,35.5))
    bezel_cut=xz_prism(bezel,-40,-32.0)
    panel=xz_prism(bezel,-32.0,-30.8)
    visor=visor-bezel_cut+panel
    optics=[{'name':'RGB','x':-22-.0290536247,'z':35.5,'inner_wh':[15.5,15.5],'fov':[112,63]},
            {'name':'TX','x':7-.0290536247,'z':35.5,'inner_wh':[12,9],'fov':[110,90]},
            {'name':'RX','x':22-.0290536247,'z':35.5,'inner_wh':[16.5,16.5],'fov':[110,110]}]
    cuts=[]
    for o in optics:
        def section(y):
            delta=max(0,-30.8-y)
            wx=o['inner_wh'][0]+2*delta*math.tan(math.radians(o['fov'][0]/2))
            wz=o['inner_wh'][1]+2*delta*math.tan(math.radians(o['fov'][1]/2))
            if o['name']=='TX':return rounded_section(wx,wz,1.2,(o['x'],o['z']))
            a=np.linspace(0,2*math.pi,129)[:-1];return md.CrossSection([np.column_stack([o['x']+wx/2*np.cos(a),o['z']+wz/2*np.sin(a)])])
        cuts.append(M.batch_hull([xz_prism(section(y),y-.0001,y+.0001) for y in [-30.7999,-32,-36]]))
        o['outer_wh_at_panel_mm']=[o['inner_wh'][j]+2*1.2*math.tan(math.radians(o['fov'][j]/2)) for j in [0,1]]
    visor-=union(cuts)
    # A genuine removable colored outline, backed by the opaque port panel.
    trim_cs=bezel-bezel.offset(-.65,circular_segments=96)
    trim=xz_prism(trim_cs,-34.25,-32.00)
    # Two 4 mm deep transverse ribs with thin vertical webs follow the shell floor.
    # Camera support is confined to its actual straight bottom, not its rear radius.
    xs=np.linspace(-30,30,81)
    lower=np.array([[x,5+14*math.exp(-(x/15)**2)+1.9] for x in xs])
    rib_poly=np.vstack([lower,[[30,22],[-30,22]]])
    ribs=union([xz_prism(md.CrossSection([rib_poly]),a,b) for a,b in [(-22,-18),(-15,-11)]])
    visor+=ribs
    # Retain original temples; replace the old front and its nasal prongs.
    temples=original^box([-120,43,-5],[120,170,70])
    old_tabs=load(R/'Headset_CompactFront_Review_2026-10-02/inputs/front_tabs.npz')
    tab_l=(old_tabs^box([-100,130,-5],[0,180,70])).translate((-5.1,0,0))
    tab_r=(old_tabs^box([0,130,-5],[100,180,70])).translate((5.1,0,0))
    bridges=union([box([-76.2,145,43],[-70.6,147.0703299,52]),box([70.6,145,43],[76.2,147.0703299,52])])
    body=union([visor,temples,tab_l,tab_r,bridges])
    # Split lower-edge cable gland: place the wire while the lid is off; a moulded
    # USB plug never has to pass through a wire-sized bore. The cable drops below
    # the rounded camera end before exiting, without an opening behind its face.
    cable_bore=cylinder_y(-41,22.5,-8,4,3.2)+box([-44.2,-8,19.65],[-37.8,4,22.5])
    body-=cable_bore
    lid-=cable_bore
    core=cylinder_y(-41,22.5,-1.6,.4,3.25)+box([-44.25,-1.6,19.65],[-37.75,.4,22.5])
    flange=cylinder_y(-41,22.5,.4,1.5,3.8)+box([-44.8,.4,19.65],[-37.2,1.5,22.5])
    gland=(core+flange)-cylinder_y(-41,22.5,-3,3,2.25)
    gland-=box([-41.2,-3,19],[-40.8,4,22.5])
    # Soft pads are separate references; install thickness as listed after the body.
    pads=union([box([x-4,a,22],[x+4,b,23]) for x in [-22,22] for a,b in [(-22,-18),(-15,-11)]]+
               [box([-20,-18,53.0],[20,-14,55.6]),
                box([-30,-5,30],[-16,-1.6,43]),box([16,-5,30],[30,-1.6,43]),
                box([-34.5,-30.8,31],[-32,-30,40]),box([32,-30.8,31],[34.5,-30,40])])
    geoms={}
    for name,m in [('front_body',body),('service_lid',lid),('visor',visor),('outer_envelope',outer),('inner_void',inner),('original_normal',original),('original_temples',temples),('shifted_tabs',tab_l+tab_r),('tab_bridges',bridges),('cradle_ribs',ribs),('service_lip',service_lip),('bezel_trim',trim),('pads',pads),('fasteners',union(bolts+nuts)),('cable_gland',gland),('service_opening',opening),('optical_cuts',union(cuts))]:geoms[name]=save(name,m)
    # Only the front endpoints of the visualization straps move; the rear is fixed.
    a=np.load(R/'Headset_Carbon6K_FlatBase_Review_2026-10-02/geometry/straps_preview.npz');sv=a['v'].copy()
    front=sv[:,1]<160;sv[front,0]+=np.sign(sv[front,0])*5.1
    np.savez_compressed(G/'straps_preview.npz',v=sv,f=a['f'])
    (G/'render_manifest.json').write_text(json.dumps({'parts':[{'name':'bezel_trim','path':'bezel_trim.npz','material':'strap'}]}),encoding='utf8')
    for name,src in [('camera','camera_physical_native.npz'),('camera_optics','camera_optics_native.npz')]:
        a=np.load(P/'inputs'/src);v=np.asarray(a['v'])@CAMERA_T[:,:3].T+CAMERA_T[:,3];out={k:a[k] for k in a.files};out['v']=v;np.savez_compressed(G/(name+'.npz'),**out)
    report={'camera_transform_native_to_wearing':CAMERA_T.tolist(),'camera_orientation':'Level, forward; physical bottom down; RGB at left in wearer coordinates.',
            'shell_wall_mm':WALL,'optic_panel_wall_mm':1.2,'camera_rear_y_mm':-5,'camera_bottom_z_mm':23,
            'nominal_clearance_mm':{'front_body_to_camera':2,'panel_to_camera_front':.8,'back_to_lid':3.4,'bottom_to_support_ribs':1.0,'roof':2.6,'side':3.0},
            'fixing':'Closed main shell and four M3x12 screws, four M3 nuts in captive hex seats; soft adjustable pads. Bottom camera hole unused.',
            'lid_seam_clearance_mm':.25,'bolt_clearance_diameter_mm':3.4,'nut_pocket_across_flats_mm':5.9,
            'usb_plug_design_envelope_mm':{'metal_nose':[3.2,8.2,2.4],'molded_body':[13,10,8],'rebate_relief_allowance':.5},
            'cable_gland_mm':{'wire_bore_diameter':4.5,'split_width':.4,'core_radius':3.25,'shell_recess_radius':3.2},
            'original_temple_preserved_from_y_mm':43,'slot_shift_each_side_mm':5.1,'unchanged_slots_y_mm':[151.5703299,154.5703299],'unchanged_slots_z_mm':[26.2,52.2],
            'optics':optics,'geometry':geoms,'source_hashes':{str(f.relative_to(R)):hashlib.sha256(f.read_bytes()).hexdigest() for f in [R/'Headset_Repro/raw/BTTF_Glasses.3mf',R/'Headset_Repro/raw/CS30_customer.stp',R/'Headset_Carbon6K_FlatBase_Review_2026-10-02/geometry/rear_unified_preview.npz',P/'inputs/camera_physical_native.npz']}}
    (G/'geometry_values.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps({k:geoms[k] for k in ['front_body','service_lid','visor']},indent=2))

if __name__=='__main__':build()
