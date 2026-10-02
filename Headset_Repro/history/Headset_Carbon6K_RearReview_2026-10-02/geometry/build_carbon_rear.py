"""Thin Carbon Battery 6K rear review, wearing axes; NPZ only."""
from pathlib import Path
import json, hashlib
import numpy as np
import manifold3d as md
P=Path(__file__).resolve().parent
ROOT=P.parents[1]
OLD=ROOT/'Headset_Elastic25_2026-10-02/rear_work'
M=md.Manifold
def load(path):
    a=np.load(path);m=M(md.Mesh64(vert_properties=np.ascontiguousarray(a['v'],dtype=np.float64),tri_verts=np.ascontiguousarray(a['f'],dtype=np.uint64)))
    assert m.status()==md.Error.NoError,(path,m.status())
    return m
def box(lo,hi):
    lo=np.array(lo,float);hi=np.array(hi,float);return M.cube(tuple(hi-lo)).translate(tuple(lo))
def save(name,m):
    a=m.to_mesh64();v=np.array(a.vert_properties)[:,:3];f=np.array(a.tri_verts)
    np.savez_compressed(P/(name+'.npz'),v=v,f=f)
    return {'bounds_xyz_mm':[v.min(0).tolist(),v.max(0).tolist()],'volume_mm3':float(m.volume()),'components':len(m.decompose()),'mesh_status':str(m.status()),'vertices':len(v),'triangles':len(f)}
def round_rect(w,h,r):
    pts=[]
    for y,z,start in [(w/2-r,h/2-r,0),(-w/2+r,h/2-r,90),(-w/2+r,-h/2+r,180),(w/2-r,-h/2+r,270)]:
        for angle in np.linspace(start,start+90,25):
            q=np.radians(angle);pts.append([y+r*np.cos(q),z+r*np.sin(q)])
    return md.CrossSection([np.array(pts)])
def x_prism(section,length,x0,y0=0,z0=0):
    # Local 2D Y,Z and extrusion X, right-handed cyclic axis permutation.
    return section.extrude(length).transform([[0,0,1,x0],[1,0,0,y0],[0,1,0,z0]])
def clip_surface(v,f,xlo,xhi,zlo,zhi):
    ov=[];of=[];lookup={}
    def idx(p):
        k=tuple(np.round(p,10))
        if k not in lookup:lookup[k]=len(ov);ov.append(p.copy())
        return lookup[k]
    for tri in v[f]:
        poly=list(tri.copy())
        for axis,bound,sgn in [(0,xlo,1),(0,xhi,-1),(2,zlo,1),(2,zhi,-1)]:
            if not poly:break
            out=[];a=poly[-1];da=sgn*(a[axis]-bound)
            for b in poly:
                db=sgn*(b[axis]-bound)
                if (da>=-1e-11)!=(db>=-1e-11):
                    p=a+(b-a)*da/(da-db);p[axis]=bound;out.append(p)
                if db>=-1e-11:out.append(b)
                a,da=b,db
            poly=out
        for j in range(1,len(poly)-1):
            if np.linalg.norm(np.cross(poly[j]-poly[0],poly[j+1]-poly[0]))>1e-12:of.append([idx(poly[0]),idx(poly[j]),idx(poly[j+1])])
    return np.array(ov),np.array(of,dtype=np.int32)
def ribbon(points,side,width=25,thickness=.8):
    pts=np.asarray(points,float);v=[]
    for q in pts:
        for d,z in [(0,-width/2),(0,width/2),(side*thickness,-width/2),(side*thickness,width/2)]:v.append(q+[d,0,z])
    f=[]
    for j in range(len(pts)-1):
        a=4*j;b=4*(j+1)
        f.extend([[a,b,b+1],[a,b+1,a+1],[a+2,b+3,b+2],[a+2,a+3,b+3],[a,a+2,b+2],[a,b+2,b],[a+1,b+1,b+3],[a+1,b+3,a+3]])
    f.extend([[0,1,3],[0,3,2],[4*(len(pts)-1),4*(len(pts)-1)+3,4*(len(pts)-1)+1],[4*(len(pts)-1),4*(len(pts)-1)+2,4*(len(pts)-1)+3]])
    v=np.array(v);f=np.array(f);vol=np.einsum('ij,ij->i',v[f[:,0]],np.cross(v[f[:,1]],v[f[:,2]])).sum()/6
    if vol<0:f=f[:,::-1]
    m=M(md.Mesh64(vert_properties=v,tri_verts=f.astype(np.uint64)));assert m.status()==md.Error.NoError
    return m
def main():
    P.mkdir(parents=True,exist_ok=True)
    report={'review_only':True,'front_unchanged':True,'head_pose_unchanged':True,'rear_replaces':'Rear_Final','battery_dimensions_mm':{'diameter':22.8,'length':90.4,'mass_g_user':88},'opening_end':'+X'}
    tray=load(OLD/'rear_tray.npz') ^ box([-20,100,25.5],[20,220,52.9])
    report['tray']=save('rear_tray',tray)
    for name in ['rear_inner_surface','rear_outer_surface']:
        a=np.load(OLD/(name+'.npz'));v,f=clip_surface(a['v'],a['f'],-20,20,25.5,52.9)
        np.savez_compressed(P/(name+'.npz'),v=v,f=f)
    # 3mm connector ribs follow exactly the previous outer anatomical surface.
    join=load(OLD/'rear_fill.npz')
    ribs=[]
    for side,name in [(-1,'left'),(1,'right')]:
        xl,xh=(-20,-17) if side<0 else (17,20)
        rib=(join ^ box([xl,100,25.5],[xh,203.4,52.9]))+box([xl,203.1,25.5],[xh,205.4,52.9])
        report[name+'_rib']=save('rear_'+name+'_rib',rib);ribs.append(rib)
    # A small horizontal 2mm connection tongue bridges the upper central gap.
    center=(join ^ box([-4,202,49.9],[4,203.4,51.9]))+box([-4,203.1,49.9],[4,204.8,51.9])
    report['center_connection']=save('rear_central_join',center)
    report['center_connection_nominal_bounds_mm']=[[-4,202,49.9],[4,204.8,51.9]]
    outer=x_prism(round_rect(27.4,27.4,3),93,-46.5,217,39.2)
    cavity=x_prism(round_rect(23.4,23.4,1),91.5,-44.5,217,39.2)
    case=outer-cavity
    # Subtractive R2 external corner blending at the3mm plate/2mm box-wall
    # L junction. The sharp2x3 L section would locally exceed3mm despite
    # nominal wall dimensions; this removes its thick outer corner.
    root_cuts=[]
    for side in [-1,1]:
        cx=side*44.5
        sq=box([44.5 if side>0 else -46.5,203.3,20],[46.5 if side>0 else -44.5,205.3,60])
        circ=M.cylinder(40,2,circular_segments=192).translate((cx,203.3,20))
        root_cuts.append(sq-circ)
    root_relief=M.batch_boolean(root_cuts,md.OpType.Add)
    case-=root_relief
    report['plate_root_outer_relief_radius_mm']=2
    save('plate_root_relief',root_relief)
    # Bottom cantilever: width8mm including slits, clear tongue6.8mm,
    # longitudinal8.4mm, 0.6mm U-shaped gaps, opening-facing tip.
    slits=[box([37.1,213,25.4],[46.4,213.6,27.6]),box([37.1,220.4,25.4],[46.4,221,27.6]),box([45.8,213,25.4],[46.4,221,27.6])]
    case-=M.batch_boolean(slits,md.OpType.Add)
    # Hook built from an XZ polygon extruded across the spring width; root
    # embeds0.05mm into the floor. Its0.8mm raised lip is behind battery end.
    hp=np.array([[45.5,27.45],[46.2,27.45],[46.2,28.3],[45.9,28.3],[45.5,27.5]])
    hook=md.CrossSection([hp]).extrude(6.8).transform([[1,0,0,0],[0,0,-1,220.4],[0,1,0,0]])
    report['hook']=save('rear_hook',hook)
    report['box_without_hook']=save('rear_box_without_hook',case)
    report['box_with_hook']=save('rear_box',case+hook)
    report['cavity']=save('battery_cavity',cavity)
    report['box_dimensions_mm']={'outer': [93,27.4,27.4],'inner':[91,23.4,23.4],'wall':2,'outer_corner_radius':3,'inner_corner_radius':1,'closed_end_x':-46.5,'closed_inner_seat_x':-44.5,'open_x':46.5,'center_y':217,'center_z':39.2,'front_y':203.3,'back_y':230.7}
    report['spring']={'u_slit_mm':.6,'tongue_width_mm':6.8,'tongue_clear_length_mm':8.7,'root_x_mm':37.1,'tip_x_mm':45.8,'hook_height_above_inner_bottom_mm':.8,'hook_top_z_mm':28.3,'hook_base_overhang_over_transverse_slit_mm':.4,'physical_deflection_not_checked':True}
    plates=[]
    for side,name in [(-1,'left'),(1,'right')]:
        xl,xh=(-46.5,-43.5) if side<0 else (43.5,46.5)
        plate=box([xl,195.3,23.2],[xh,203.5,55.2])-box([xl-1,198.3,26.2],[xh+1,201.3,52.2])-root_relief
        report[name+'_strap_plate']=save('rear_'+name+'_strap_plate',plate);plates.append(plate)
    report['strap_plate']={'thickness_mm':3,'height_mm':32,'y_range_mm':[195.3,203.5],'slot_y_mm':[198.3,201.3],'slot_z_mm':[26.2,52.2],'slot_mm':[26,3],'x_ranges_mm':[[-46.5,-43.5],[43.5,46.5]]}
    rear_nohook=M.batch_boolean([tray,case,center,*ribs,*plates],md.OpType.Add)
    rear=rear_nohook+hook
    report['rear_without_hook']=save('rear_without_hook',rear_nohook)
    report['rear']=save('rear_unified_preview',rear)
    assert len(rear.decompose())==1,(rear.status(),len(rear.decompose()))
    # Real-dimension cylinder, axis+X; fully seated against closed end.
    battery=M.cylinder(90.4,11.4,circular_segments=192).transform([[0,0,1,-44.5],[1,0,0,217],[0,1,0,39.2]])
    report['battery']=save('battery_preview',battery)
    report['battery_axis_endpoints_mm']=[[-44.5,217,39.2],[45.9,217,39.2]]
    straps=[];free=[];paths={}
    for side,name,sx in [(-1,'left',-71.0974706),(1,'right',71.1061337)]:
        start=np.array([sx,159.0703299,39.2]);anchor=np.array([side*46.5,198.3,39.2]);slot=np.array([sx,154.5703299,39.2])
        m=ribbon([slot,start,anchor],side);fm=ribbon([start,anchor],side)
        straps.append(m);free.append(fm)
        save('strap_'+name,m);save('free_strap_'+name,fm)
        paths[name]={'front_slot_exit_xyz_mm':slot.tolist(),'free_start_xyz_mm':start.tolist(),'free_end_xyz_mm':anchor.tolist(),'free_length_mm':float(np.linalg.norm(anchor-start)),'slot_to_slot_centerline_length_mm':float(np.linalg.norm(anchor-start)+4.5),'band_width_mm':25,'illustrative_thickness_mm':.8,'front_arm_shortening_mm':0}
    save('straps_preview',M.batch_boolean(straps,md.OpType.Add));save('free_straps',M.batch_boolean(free,md.OpType.Add))
    report['strap_paths']=paths
    (P/'strap_paths.json').write_text(json.dumps(paths,indent=2),encoding='utf-8')
    report['thin_wall_construction']='Empty cylindrical-battery cavity. Thin tray2.5, box2 with concentric corner radii3/1, plates3, ribs3, upper central tongue2. No bulk fill between box and tray. Local junction thickness and physical spring behavior require independent audit.'
    report['sources']={'old_curved_tray':str(OLD/'rear_tray.npz'),'joining_surface_boundary':str(OLD/'rear_fill.npz'),'head':str(ROOT/'Headset_FullCase_30mm_Preview_2026-10-02/headform/Medium_Trial_Registered.npz'),'front':str(ROOT/'Headset_ThinShell_Review_2026-10-02/geometry/front_unified_preview.npz')}
    (P/'geometry_values.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()
