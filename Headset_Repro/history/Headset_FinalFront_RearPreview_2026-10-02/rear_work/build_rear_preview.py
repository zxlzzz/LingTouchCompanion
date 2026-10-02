"""Authorized rear-part NPZ preview. Preserve existing box and head registration.

Dependencies: numpy, manifold3d. No STL/3MF/printing files are exported.
Original box/notch/bump are reused exactly. The old bulk fill is excluded;
only two narrow connector ribs and a small central joining patch remain.
"""
from pathlib import Path
import hashlib, json, shutil
import numpy as np
import manifold3d as md

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
OLD=ROOT/'Headset_Elastic25_2026-10-02/rear_work'
M=md.Manifold

def load(path):
    a=np.load(path)
    m=M(md.Mesh64(vert_properties=np.ascontiguousarray(a['v'],dtype=np.float64),tri_verts=np.ascontiguousarray(a['f'],dtype=np.uint64)))
    assert m.status()==md.Error.NoError,(str(path),m.status())
    return m

def box(lo,hi):
    lo=np.array(lo,float);hi=np.array(hi,float)
    return M.cube(tuple(hi-lo)).translate(tuple(lo))

def save(name,m):
    mesh=m.to_mesh64();v=np.array(mesh.vert_properties)[:,:3];f=np.array(mesh.tri_verts)
    np.savez_compressed(HERE/(name+'.npz'),v=v,f=f)
    return {'vertices':len(v),'triangles':len(f),'bounds_xyz_mm':[v.min(0).tolist(),v.max(0).tolist()],'solid_volume_mm3':float(m.volume()),'connected_components':len(m.decompose()),'mesh_status':str(m.status())}

def clip_surface_x(vertices,faces,low,high):
    """Clip actual old triangles, preserving linear surfaces and connectivity."""
    outv=[];outf=[];index={}
    def vi(p):
        key=tuple(np.round(p,10))
        if key not in index:index[key]=len(outv);outv.append(p.copy())
        return index[key]
    for tri in vertices[faces]:
        poly=[p.copy() for p in tri]
        for bound,sign in [(low,1),(high,-1)]:
            if not len(poly):break
            updated=[];a=poly[-1];da=sign*(a[0]-bound)
            for b in poly:
                db=sign*(b[0]-bound)
                if (da>=-1e-12)!=(db>=-1e-12):
                    p=a+(b-a)*da/(da-db);p[0]=bound;updated.append(p)
                if db>=-1e-12:updated.append(b)
                a,da=b,db
            poly=updated
        for j in range(1,len(poly)-1):
            p,q,r=poly[0],poly[j],poly[j+1]
            if np.linalg.norm(np.cross(q-p,r-p))<1e-13:continue
            outf.append([vi(p),vi(q),vi(r)])
    return np.array(outv),np.array(outf,dtype=np.int32)

def main():
    report={'preview_only':True,'print_file_exported':False,'front_unchanged':True,'head_registration_unchanged':True,'head_source':str(ROOT/'Headset_FullCase_30mm_Preview_2026-10-02/headform/Medium_Trial_Registered.npz')}
    original=load(OLD/'rear_tray.npz')
    tray=original ^ box([-40,110,8.1],[40,204,55.3])
    assert tray.status()==md.Error.NoError
    report['tray']=save('rear_tray',tray)
    for name in ['rear_inner_surface','rear_outer_surface']:
        old=np.load(OLD/(name+'.npz'));v,f=clip_surface_x(old['v'],old['f'],-40,40)
        np.savez_compressed(HERE/(name+'.npz'),v=v,f=f)
        edges=np.vstack([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]])
        report[name]={'vertices':len(v),'triangles':len(f),'bounds_xyz_mm':[v.min(0).tolist(),v.max(0).tolist()],'max_triangle_edge_mm':float(np.linalg.norm(v[edges[:,0]]-v[edges[:,1]],axis=1).max()),'source':'Exact clipped old original-head-derived triangular surface; no new curve or head registration.'}
    # A former bridge stores the actual curved joining boundary inside the
    # tray wall. Intersect only the two3mm strips; never include its bulk.
    joinboundary=load(OLD/'rear_fill.npz')
    ribright=joinboundary ^ box([37,110,8.1],[40,203.4,55.3])
    ribleft=joinboundary ^ box([-40,110,8.1],[-37,203.4,55.3])
    report['right_rib']=save('rear_right_rib',ribright)
    report['left_rib']=save('rear_left_rib',ribleft)
    report['rib_x_thickness_mm']=3.
    # Existing outer tray at its closest point endsY203.2444366, while the
    # untouched box startsY203.3. This tiny upper-central patch connects them.
    centerjoin=joinboundary ^ box([-4,202,51.2],[4,203.4,55.3])
    report['central_join']=save('rear_central_join',centerjoin)
    report['central_join_region_xz_mm']=[[-4,51.2],[4,55.2]]
    report['minimum_original_center_gap_y_mm']=203.3-203.24443660487455
    case=load(OLD/'rear_box.npz')
    # Preserve the actual box, notch, bump, battery preview byte-for-byte.
    for filename in ['rear_box.npz','battery_preview.npz']:
        shutil.copy2(OLD/filename,HERE/filename)
    case_mesh=case.to_mesh64();case_vertices=np.array(case_mesh.vert_properties)[:,:3]
    report['box']={'vertices':len(case_vertices),'triangles':len(case_mesh.tri_verts),'bounds_xyz_mm':[case_vertices.min(0).tolist(),case_vertices.max(0).tolist()],'solid_volume_mm3':float(case.volume()),'connected_components':len(case.decompose()),'mesh_status':str(case.status())}
    report['box_source_sha256']=hashlib.sha256((OLD/'rear_box.npz').read_bytes()).hexdigest()
    report['box_copy_sha256']=hashlib.sha256((HERE/'rear_box.npz').read_bytes()).hexdigest()
    assert report['box_source_sha256']==report['box_copy_sha256']
    ears=[];roots=[];slots=[]
    for side,name in [(-1,'left'),(1,'right')]:
        if side>0:
            ear=box([65.3,200.3,23.2],[68.3,211.3,55.2]);root=box([60.7,207,23.2],[66.3,211.3,55.2]);slot=box([64.3,203.3,26.2],[69.3,206.3,52.2])
        else:
            ear=box([-68.3,200.3,23.2],[-65.3,211.3,55.2]);root=box([-66.3,207,23.2],[-60.7,211.3,55.2]);slot=box([-69.3,203.3,26.2],[-64.3,206.3,52.2])
        ear-=slot
        report[name+'_ear']=save('rear_'+name+'_ear',ear)
        report[name+'_ear_root']=save('rear_'+name+'_ear_root',root)
        ears.append(ear);roots.append(root);slots.append(slot)
    report['ear_x_thickness_mm']=3.
    report['slot_dimensions_z_y_mm']=[26,3]
    report['slot_y_mm']=[203.3,206.3]
    report['slot_z_mm']=[26.2,52.2]
    report['slot_cut_axis']='X'
    report['band_outer_front_edge_contacts_xyz_mm']={'left':[-68.3,203.3,39.2],'right':[68.3,203.3,39.2]}
    report['ear_root_y_mm']=[207,211.3]
    parts=[tray,case,ribleft,ribright,centerjoin,*ears,*roots]
    rear=M.batch_boolean(parts,md.OpType.Add)
    assert rear.status()==md.Error.NoError and len(rear.decompose())==1,(rear.status(),len(rear.decompose()))
    report['unified']=save('rear_unified_preview',rear)
    report['unified_sha256']=hashlib.sha256((HERE/'rear_unified_preview.npz').read_bytes()).hexdigest()
    report['old_bulk_fill_excluded']=True
    report['source_references']={'original_tray':str(OLD/'rear_tray.npz'),'joining_boundary_only':str(OLD/'rear_fill.npz'),'unchanged_box':str(OLD/'rear_box.npz')}
    report['notes']='Preview only. Tray narrowed80mm, former end slots removed. Two3mm wide full47mm height ribs and tiny upper central patch replace former bulkfill. Box and original battery preview remain unchanged. Ribs/ear strength and complete strap path are not asserted by this build.'
    (HERE/'rear_values.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))

if __name__=='__main__':main()
