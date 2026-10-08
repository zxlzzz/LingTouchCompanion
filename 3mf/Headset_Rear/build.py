"""Regenerate the unchanged rear assembly from genuine anatomical source meshes.

Only rear_body and battery meshes required by the final build are emitted.
The original rear body vertex and triangle hashes are asserted before saving.
"""
from pathlib import Path
import json, hashlib
import numpy as np
import manifold3d as md
P=Path(__file__).resolve().parent
ROOT=P.parent
G=P/'geometry';G.mkdir(exist_ok=True)
OLD=P/'inputs'
PROVENANCE=json.loads((P/'source_provenance.json').read_text(encoding='utf8'))
OUTPUT_NAMES={'rear_unified_preview':'rear_body','battery_preview':'battery'}
M=md.Manifold
def load(path):
    a=np.load(path);m=M(md.Mesh64(vert_properties=np.ascontiguousarray(a['v'],dtype=np.float64),tri_verts=np.ascontiguousarray(a['f'],dtype=np.uint64)))
    assert m.status()==md.Error.NoError,(path,m.status())
    return m
def box(lo,hi):
    lo=np.array(lo,float);hi=np.array(hi,float);return M.cube(tuple(hi-lo)).translate(tuple(lo))
def save(name,m):
    a=m.to_mesh64();v=np.array(a.vert_properties)[:,:3];f=np.array(a.tri_verts)
    if name in OUTPUT_NAMES:
        output=OUTPUT_NAMES[name]
        actual={key:hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest() for key,a in [('v',v),('f',f)]}
        assert actual==PROVENANCE['unchanged_meshes'][output]['array_sha256'],f'{output}: source geometry changed'
        np.savez_compressed(G/(output+'.npz'),v=v,f=f)
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
def main():
    P.mkdir(parents=True,exist_ok=True)
    report={'review_only':True,'front_unchanged':False,'head_pose_unchanged':True,'rear_replaces':'Carbon6K top-open review before end-wall and flat-base correction','battery_dimensions_mm':{'diameter':22.8,'length':90.4,'mass_g_user':88},'opening_end':'+Z'}
    tray=load(OLD/'rear_tray.npz') ^ box([-20,100,25.5],[20,220,52.9])
    report['tray']=save('rear_tray',tray)
    # 3mm connector ribs follow exactly the previous outer anatomical surface.
    join=load(OLD/'rear_fill.npz')
    ribs=[]
    for side,name in [(-1,'left'),(1,'right')]:
        xl,xh=(-20,-17) if side<0 else (17,20)
        rib=(join ^ box([xl,100,25.5],[xh,203.4,52.9]))+box([xl,203.1,25.5],[xh,205.4,52.9])
        report[name+'_rib']=save('rear_'+name+'_rib',rib);ribs.append(rib)
    # A small horizontal 2mm connection tongue bridges the lower central gap.
    center=(join ^ box([-4,100,25.5],[4,203.4,27.5]))+box([-4,203.1,25.5],[4,204.8,27.5])
    report['center_connection']=save('rear_central_join',center)
    report['center_connection_nominal_bounds_mm']=[[-4,100,25.5],[4,204.8,27.5]]
    outer=x_prism(round_rect(27.4,27.4,3),95,-47.5,217,39.2)
    cavity=x_prism(round_rect(23.4,23.4,1),91,-45.5,217,39.2)
    # Both X ends retain2mm walls; the whole91x23.4 mouth is open upward.
    cavity+=box([-45.5,205.3,39.2],[45.5,228.7,100])
    case=outer-cavity
    port_notch=box([45.49,211,36.2],[48,223,42.2])
    case-=port_notch
    report['interface_opening_mm']={'end':'+X','width_y':12,'height_z':6,'y_range':[211,223],'z_range':[36.2,42.2],'actual_usb_and_plug_geometry':'Not measured; nominal small window only.'}
    # Subtractive R1.5 external corner blending at the3mm plate/2mm box-wall
    # L junction. The sharp2x3 L section would locally exceed3mm despite
    # nominal wall dimensions; this removes its thick outer corner.
    root_cuts=[]
    for side in [-1,1]:
        cx=side*44.5
        sq=box([44.5 if side>0 else -46.5,203.3,20],[46.5 if side>0 else -44.5,205.3,60])
        circ=M.cylinder(40,1.5,circular_segments=192).translate((cx,203.3,20))
        root_cuts.append(sq-circ)
    root_relief=M.batch_boolean(root_cuts,md.OpType.Add)
    case-=root_relief
    report['plate_root_outer_relief_radius_mm']=1.5
    save('plate_root_relief',root_relief)
    # Back-wall upright spring replaces the old bottom/axial catch. Its
    #0.8mm lip sits above the round battery's equator, permitting elastic
    # downward insertion and catching upward lift after about0.27mm play.
    slits=[];rear_hooks=[];spring_bodies=[];rear_flex_sweeps=[]
    # Two1mm upright tongues, each16mm long, released from the outer wall.
    # Projection1.4 minus the full0.6 transverse clearance leaves0.8 capture.
    for cx in [-29.,29.]:
        xl,xh=cx-14,cx+14
        slits.extend([box([xl-.6,228.6,33.65],[xl,230.8,46.25]),box([xh,228.6,33.65],[xh+.6,230.8,46.25]),box([xl-.6,228.6,45.65],[xh+.6,230.8,46.25]),box([xl,229.7,33.65],[xh,230.8,45.65])])
        hp=np.array([[228.75,43.4],[228.7,43.45],[227.3,44.85],[227.3,45.0],[228.7,45.65],[228.75,45.65]])
        rear_hooks.append(x_prism(md.CrossSection([hp[::-1]]),28,xl))
        body=box([xl,228.7,33.65],[xh,229.7,45.65]);spring_bodies.append(body)
        # The flexing wall section starts here; roots themselves remain fixed.
        segments=[]
        for z0,z1 in zip(np.linspace(33.65,45.65,65)[:-1],np.linspace(33.65,45.65,65)[1:]):
            if z1==45.65:pass
            q0=(z0-33.65)/12;q1=(z1-33.65)/16
            a=box([xl,228.7,z0],[xh,229.7,z1]);v=np.array(a.to_mesh64().vert_properties)[:,:3]
            q=(v[:,2]-33.65)/12;v[:,1]+=1.4*q*q*(3-q)/2
            b=M(md.Mesh64(vert_properties=v,tri_verts=np.array(a.to_mesh64().tri_verts)))
            if z0>33.65:segments.append(M.batch_hull([a,b]))
        ha=rear_hooks[-1]; hm=ha.to_mesh64(); hv=np.array(hm.vert_properties)[:,:3]; hq=(hv[:,2]-33.65)/12; hv[:,1]+=1.4*hq*hq*(3-hq)/2
        hb=M(md.Mesh64(vert_properties=hv,tri_verts=np.array(hm.tri_verts))); segments.append(M.batch_hull([ha,hb]))
        rear_flex_sweeps.append(M.batch_boolean(segments,md.OpType.Add))
    case-=M.batch_boolean(slits,md.OpType.Add)
    # Hook built from a YZ polygon extruded across the spring width; root
    # embeds0.05mm into the rear wall. Its0.8mm lip catches upward lift.
    hook=M.batch_boolean(rear_hooks,md.OpType.Add)
    report['hook']=save('rear_hook',hook)
    report['box_without_hook']=save('rear_box_without_hook',case)
    report['box_with_hook']=save('rear_box',case+hook)
    report['cavity']=save('battery_cavity',cavity)
    report['box_dimensions_mm']={'outer': [95,27.4,27.4],'inner':[91,23.4,25.4],'original_battery_fit_envelope':[91,23.4,23.4],'top_wall_removed_depth_increase_mm':2,'wall':2,'outer_corner_radius':3,'inner_corner_radius':1,'closed_outer_ends_x':[-47.5,47.5],'inner_ends_x':[-45.5,45.5],'top_open_z':52.9,'top_open_xy_bounds':[[-45.5,205.3],[45.5,228.7]],'center_y':217,'center_z':39.2,'front_y':203.3,'back_y':230.7}
    report['spring']={'centers_x_mm':[-29,29],'u_slit_mm':.6,'tongue_width_mm':28,'tongue_length_mm':12,'tongue_thickness_mm':1,'root_z_mm':33.65,'tip_z_mm':45.65,'hook_inward_projection_mm':1.4,'capture_after_full_lateral_clearance_mm':.8,'hook_z_range_mm':[44.85,45.65],'maximum_required_deflection_mm':1.4,'strain_formula_value':3*1*1.4/(2*12**2),'physical_deflection_not_checked':True}
    plates=[]
    for side,name in [(-1,'left'),(1,'right')]:
        xl,xh=(-46.5,-43.5) if side<0 else (43.5,46.5)
        plate=box([xl,195.3,25.5],[xh,203.5,57.5])-box([xl-1,198.3,28.5],[xh+1,201.3,54.5])-root_relief
        report[name+'_strap_plate']=save('rear_'+name+'_strap_plate',plate);plates.append(plate)
    report['strap_plate']={'thickness_mm':3,'height_mm':32,'base_z_mm':25.5,'bottom_slot_margin_mm':3,'upper_slot_margin_mm':3,'y_range_mm':[195.3,203.5],'slot_y_mm':[198.3,201.3],'slot_z_mm':[28.5,54.5],'slot_center_z_mm':41.5,'front_slot_center_z_difference_mm':2.3,'slot_mm':[26,3],'x_ranges_mm':[[-46.5,-43.5],[43.5,46.5]]}
    rear_nohook=M.batch_boolean([tray,case,center,*ribs,*plates],md.OpType.Add)
    rear=rear_nohook+hook
    report['rear_without_hook']=save('rear_without_hook',rear_nohook)
    report['rear']=save('rear_unified_preview',rear)
    assert len(rear.decompose())==1,(rear.status(),len(rear.decompose()))
    save('rear_spring_bodies',M.batch_boolean(spring_bodies,md.OpType.Add))
    save('rear_without_springs',rear-M.batch_boolean([*spring_bodies,hook],md.OpType.Add))
    save('rear_spring_motion',M.batch_boolean(rear_flex_sweeps,md.OpType.Add))
    # Real-dimension cylinder, axis+X; centered with0.3mm axial clearance at both ends.
    battery=M.cylinder(90.4,11.4,circular_segments=192).transform([[0,0,1,-45.2],[1,0,0,217],[0,1,0,39.2]])
    report['battery']=save('battery_preview',battery)
    report['battery_axis_endpoints_mm']=[[-45.2,217,39.2],[45.2,217,39.2]]
    report['thin_wall_construction']='Empty cylindrical-battery cavity. Thin tray2.5, box2 with concentric corner radii3/1, plates3, ribs3, lower central tongue2. No bulk fill between box and tray. Local junction thickness and physical spring behavior require independent audit.'
    current={'rear_redesigned':False,'wearing_coordinates_preserved':True,
             'rear_body':report['rear'],'battery':report['battery'],
             'battery_dimensions_mm':report['battery_dimensions_mm'],
             'battery_axis_endpoints_mm':report['battery_axis_endpoints_mm'],
             'box_dimensions_mm':report['box_dimensions_mm'],
             'spring':report['spring'],'strap_plate':report['strap_plate'],
             'thin_wall_construction':report['thin_wall_construction'],
             'sources':{key:row['file'] for key,row in PROVENANCE['generator_inputs'].items()},
             'registered_head_source':'Headset_Inputs/Medium_Trial_Registered.npz',
             'all_output_arrays_equal_original':True}
    (G/'geometry_values.json').write_text(json.dumps(current,indent=2),encoding='utf8')
    print(json.dumps({'rear_body':current['rear_body'],'all_output_arrays_equal_original':True},indent=2))
if __name__=='__main__':main()



