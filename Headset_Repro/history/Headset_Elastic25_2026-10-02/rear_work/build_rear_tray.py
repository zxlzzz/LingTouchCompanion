"""Rear tray preview from original anatomical triangles, no print exports."""
from pathlib import Path
import json,numpy as np
from rear_surface import offset_rear_points
P=Path(__file__).resolve().parent
xs=np.linspace(-72.8,72.8,293)
zs=np.unique(np.r_[np.linspace(8.2,55.2,95),[26.2,26.7,39.2,51.7,52.2]])
xx,zz=np.meshgrid(xs,zs);target=np.column_stack([xx.ravel(),zz.ravel()])
inner,inorm,ifaces,ierror=offset_rear_points(target,1.,iterations=50)
outer,onorm,ofaces,oerror=offset_rear_points(target,3.5,iterations=50)
# Prescribe target boundary coordinates; residual captures offset-solver error.
inner[:,[0,2]]=target;outer[:,[0,2]]=target
nx,nz=len(xs),len(zs)
faces=[]
for j in range(nz-1):
    for i in range(nx-1):
        a=j*nx+i;b=a+1;c=a+nx;d=c+1
        faces.extend([[a,b,c],[b,d,c]])
faces=np.array(faces,dtype=np.int32)
base_count=len(inner)
refinement=[]
for iteration in range(8):
    edges=np.vstack([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]]);uedges=np.unique(np.sort(edges,axis=1),axis=0)
    length=np.maximum(np.linalg.norm(inner[uedges[:,0]]-inner[uedges[:,1]],axis=1),np.linalg.norm(outer[uedges[:,0]]-outer[uedges[:,1]],axis=1))
    selected=uedges[length>1.2]
    refinement.append({'iteration':iteration,'selected_edges':len(selected),'max_world_edge_mm':float(length.max())})
    if not len(selected):break
    targets=(target[selected[:,0]]+target[selected[:,1]])/2
    iv,inn,ifi,ie=offset_rear_points(targets,1.)
    ov,onn,ofi,oe=offset_rear_points(targets,3.5)
    start=len(inner);midmap={tuple(edge):start+i for i,edge in enumerate(selected)}
    target=np.vstack([target,targets]);inner=np.vstack([inner,iv]);outer=np.vstack([outer,ov]);inorm=np.vstack([inorm,inn]);onorm=np.vstack([onorm,onn]);ifaces=np.r_[ifaces,ifi];ofaces=np.r_[ofaces,ofi];ierror=np.r_[ierror,ie];oerror=np.r_[oerror,oe]
    updated=[]
    for a,b,c in faces:
        m=midmap.get(tuple(sorted((a,b))));n=midmap.get(tuple(sorted((b,c))));p=midmap.get(tuple(sorted((c,a))))
        code=(m is not None)+2*(n is not None)+4*(p is not None)
        if code==0:updated.append([a,b,c])
        elif code==1:updated.extend([[a,m,c],[m,b,c]])
        elif code==2:updated.extend([[b,n,a],[n,c,a]])
        elif code==4:updated.extend([[c,p,b],[p,a,b]])
        elif code==3:updated.extend([[b,n,m],[a,m,c],[m,n,c]])
        elif code==6:updated.extend([[c,p,n],[b,n,a],[n,p,a]])
        elif code==5:updated.extend([[a,m,p],[c,p,b],[p,m,b]])
        else:updated.extend([[a,m,p],[m,b,n],[p,n,c],[m,n,p]])
    faces=np.array(updated,dtype=np.int32)
n=len(inner);allv=np.vstack([inner,outer])
allf=[faces,faces[:,::-1]+n]
edges=np.vstack([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]])
unordered=np.sort(edges,axis=1);_,ids,count=np.unique(unordered,axis=0,return_index=True,return_counts=True)
boundary=edges[ids[count==1]]
caps=[]
for a,b in boundary:caps.extend([[b,a,a+n],[b,a+n,b+n]])
allf.append(np.array(caps,dtype=np.int32));allf=np.vstack(allf)
np.savez_compressed(P/'rear_inner_surface.npz',v=inner,f=faces)
np.savez_compressed(P/'rear_outer_surface.npz',v=outer,f=faces[:,::-1])
np.savez_compressed(P/'rear_tray.npz',v=allv,f=allf)
np.savez_compressed(P/'rear_grid.npz',x=xs,z=zs,inner=inner[:base_count].reshape(nz,nx,3),outer=outer[:base_count].reshape(nz,nx,3),inner_original_head_face=ifaces[:base_count].reshape(nz,nx),outer_original_head_face=ofaces[:base_count].reshape(nz,nx),inner_normal=inorm[:base_count].reshape(nz,nx,3),outer_normal=onorm[:base_count].reshape(nz,nx,3))
np.savez_compressed(P/'rear_surface_targets.npz',xz=target,inner_original_head_face=ifaces,outer_original_head_face=ofaces,inner_exact_normal=inorm,outer_exact_normal=onorm)
outer_max=float(np.nanmax(outer[:,1]));front_y=float(np.ceil(outer_max*10)/10)
report={'preview_only':True,'head_unchanged':True,'z_limits_mm':[8.2,55.2],'height_mm':47.,'x_limits_mm':[-72.8,72.8],'width_mm':145.6,
 'nominal_inner_head_normal_offset_mm':1.,'nominal_outer_head_normal_offset_mm':3.5,'nominal_wall_mm':2.5,
 'vertices_per_surface':n,'faces_per_surface':len(faces),'closed_tray_vertices':len(allv),'closed_tray_triangles':len(allf),
 'inner_grid_max_world_edge_mm':float(np.linalg.norm(inner[faces]-np.roll(inner[faces],1,axis=1),axis=2).max()),
 'outer_grid_max_world_edge_mm':float(np.linalg.norm(outer[faces]-np.roll(outer[faces],1,axis=1),axis=2).max()),
 'inner_offset_solver_max_residual_mm':float(np.nanmax(ierror)),'outer_offset_solver_max_residual_mm':float(np.nanmax(oerror)),
 'missing_inner_nodes':int(np.isnan(inner).any(1).sum()),'missing_outer_nodes':int(np.isnan(outer).any(1).sum()),
 'refinement':refinement,
 'inner_bounds_xyz_mm':[inner.min(0).tolist(),inner.max(0).tolist()],'outer_bounds_xyz_mm':[outer.min(0).tolist(),outer.max(0).tolist()],
 'pocket_interface':{'outer_front_plane_y_mm':front_y,'outer_back_plane_y_mm':front_y+19.6,'outer_x_mm':[-60.8,60.8],'outer_z_mm':[8.2,55.2],'inner_x_mm':[-58.8,58.8],'inner_y_mm':[front_y+2,front_y+17.6],'inner_z_mm':[10.2,55.2],'fill_bridge':'Within|X|<=60.8,Z8.2..55.2,fill from tray outer surface to outer_front_planeY. Tray outer-maxY<=front plane prevents flat pocket from entering head. Shape should be Boolean joined to tray and box.',
 'slot_reference_file':'rear_slot_contacts.json'},
 'validation_status':'Exact original-triangle distance levels queried; maximum surface edge refined below1.2mm. Continuous triangle clearance bound and actual wall verification recorded separately.'}
(P/'rear_tray_interface.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
