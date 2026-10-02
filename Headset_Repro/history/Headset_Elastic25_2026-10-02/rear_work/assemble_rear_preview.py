"""Join curved head tray, solid fill and open power-bank box for review only."""
from pathlib import Path
import json
import numpy as np
import manifold3d as md
import trimesh
P=Path(__file__).resolve().parent;M=md.Manifold
def load(name):
 a=np.load(P/(name+'.npz'));return M(md.Mesh64(vert_properties=np.ascontiguousarray(a['v'],dtype=np.float64),tri_verts=np.ascontiguousarray(a['f'],dtype=np.uint64)))
def box(lo,hi):
 lo=np.array(lo,float);hi=np.array(hi,float);return M.cube(tuple(hi-lo)).translate(tuple(lo))
def save(name,m):
 me=m.to_mesh64();np.savez_compressed(P/(name+'.npz'),v=np.array(me.vert_properties)[:,:3],f=np.array(me.tri_verts))
def loft(xs,zs,start_y,end_y):
 nx,nz=len(xs),len(zs);xx,zz=np.meshgrid(xs,zs)
 v=np.vstack([np.column_stack([xx.ravel(),start_y.ravel(),zz.ravel()]),np.column_stack([xx.ravel(),np.full(nx*nz,end_y),zz.ravel()])]);n=nx*nz;f=[]
 for j in range(nz-1):
  for i in range(nx-1):
   a=j*nx+i;b=a+1;c=a+nx;d=c+1
   f.extend([[a,b,c],[b,d,c],[a+n,c+n,b+n],[b+n,c+n,d+n]])
 for a,b in [(i,i+1) for i in range(nx-1)]+[(j*nx+nx-1,(j+1)*nx+nx-1) for j in range(nz-1)]+[(j*nx,(j+1)*nx) for j in range(nz-1)]+[((nz-1)*nx+i,(nz-1)*nx+i+1) for i in range(nx-1)]:
  f.extend([[a,b,b+n],[a,b+n,a+n]])
 me=trimesh.Trimesh(v,np.array(f),process=True);trimesh.repair.fix_normals(me,multibody=True)
 return M(md.Mesh64(vert_properties=np.ascontiguousarray(me.vertices,dtype=np.float64),tri_verts=np.ascontiguousarray(me.faces,dtype=np.uint64)))
g=np.load(P/'rear_grid.npz');interface=json.loads((P/'rear_tray_interface.json').read_text());tray=load('rear_tray')
assert tray.status()==md.Error.NoError,str(tray.status())
xs=np.unique(np.r_[-60.8,g['x'][(g['x']>-60.8)&(g['x']<60.8)],60.8]);zs=g['z']
start=np.array([(3*np.interp(xs,g['x'],outer[:,1])+np.interp(xs,g['x'],inner[:,1]))/4 for inner,outer in zip(g['inner'],g['outer'])])
py=interface['pocket_interface']['outer_front_plane_y_mm'];z0=8.2;ztop=55.2
bridge=loft(xs,zs,start,py+.1);assert bridge.status()==md.Error.NoError
case=box([-60.8,py,z0],[60.8,py+19.6,ztop])-box([-58.8,py+2,z0+2],[58.8,py+17.6,ztop+.1])
case-=box([58.7,py+4.3,ztop-35],[60.9,py+15.3,ztop+.1])
case+=M.sphere(1,48).scale((1,.8,.8)).translate((0,py+2,ztop-1.5))
slots=[];slot_info=[]
slot_rows=zs[(zs>=26.2-1e-8)&(zs<=52.2+1e-8)]
for x in [-66.8,66.8]:
 vv=[];row_info=[]
 for z in slot_rows:
  j=int(np.argmin(abs(zs-z)));oy=np.interp(x,g['x'],g['outer'][j,:,1]);iy=np.interp(x,g['x'],g['inner'][j,:,1])
  gradient=np.gradient(g['outer'][j,:,1],g['x']);slope=np.interp(x,g['x'],gradient)
  tangent=np.array([1.,slope,0.]);tangent/=np.linalg.norm(tangent);normal=np.array([-tangent[1],tangent[0],0.]);center=np.array([x,(oy+iy)/2,z])
  for a,b in [(-1,-1),(1,-1),(1,1),(-1,1)]:vv.append(center+a*1.5*tangent+b*20*normal)
  row_info.append({'z':float(z),'center':center.tolist(),'horizontal_tangent':tangent.tolist(),'horizontal_normal':normal.tolist(),'cut_width_tangent':3.})
 ff=[]
 for j in range(len(slot_rows)-1):
  for k in range(4):
   a=j*4+k;b=j*4+(k+1)%4;c=(j+1)*4+k;d=(j+1)*4+(k+1)%4;ff.extend([[a,b,c],[b,d,c]])
 ff.extend([[0,2,1],[0,3,2]]);a=(len(slot_rows)-1)*4;ff.extend([[a,a+1,a+2],[a,a+2,a+3]])
 me=trimesh.Trimesh(vv,ff,process=True);trimesh.repair.fix_normals(me,multibody=True)
 cut=M(md.Mesh64(vert_properties=np.ascontiguousarray(me.vertices,dtype=np.float64),tri_verts=np.ascontiguousarray(me.faces,dtype=np.uint64)));assert cut.status()==md.Error.NoError
 slots.append(cut);slot_info.append({'center_x':x,'rows':row_info})
slotcut=M.batch_boolean(slots,md.OpType.Add)
# Width3 is measured along the local horizontal tangent, not globalX.
tray_with_slots=tray-slotcut
rear=M.batch_boolean([tray_with_slots,bridge,case],md.OpType.Add)
assert rear.status()==md.Error.NoError and len(rear.decompose())==1,(rear.status(),len(rear.decompose()))
save('rear_tray_with_slots',tray_with_slots);save('rear_box',case);save('rear_fill',bridge);save('rear_unified_preview',rear)
save('battery_preview',box([-58.5,py+2.3,z0+2],[58.5,py+17.3,ztop+2]))
v=np.array(rear.to_mesh64().vert_properties)[:,:3]
report={'preview_only':True,'rear_print_file_exported':False,'single_closed_connected_piece':True,'rear_bounds_xyz_mm':[v.min(0).tolist(),v.max(0).tolist()],
 'rear_width_mm':145.6,'rear_y_bounding_span_mm':float(np.ptp(v[:,1])),'rear_z_span_mm':47.,'slot_height_width_mm':[26.,3.],
 'box_inner_width_depth_height_mm':[117.6,15.6,45.],'box_wall_mm':2.,'battery_top_exposure_mm':2.,'bump_inward_mm':.8,'port_notch_width_depth_mm':[11.,35.],
 'port_notch_z_mm':[20.2,55.2],'tray_z_mm':[8.2,55.2],'fill_volume_mm3':float(bridge.volume()),'rear_solid_volume_mm3':float(rear.volume()),
 'slot_note':'Slots26 inZ,3 along local horizontal tangent; cutting axis is the local horizontal normal. The3mm dimension is a tangent projection, not curved-surface arc length.',
 'front_position_unresolved':True}
(P/'rear_assembly_values.json').write_text(json.dumps(report,indent=2),encoding='utf8');print(json.dumps(report,indent=2))
(P/'rear_slot_geometry.json').write_text(json.dumps(slot_info,indent=2),encoding='utf8')
