"""Inspect local official NIOSH meshes without changing the source dataset."""
from pathlib import Path
import zipfile, re, json
import numpy as np
from scipy.spatial import ConvexHull

HERE=Path(__file__).resolve().parent
ZIP=HERE.parents[1]/'Headset_Layout_v15/reference/rd-10130-2020-0.zip'
REPORT={}
with zipfile.ZipFile(ZIP) as z:
    for size in ['small','medium','large','Long_narrow','Short_Wide']:
        name=next(n for n in z.namelist() if n.endswith('/'+size+'_symmetry.stl'))
        data=z.read(name)
        raw=np.fromstring(re.sub(rb'\s*vertex\s+',b' ',b' '.join(re.findall(rb'vertex\s+([^\r\n]+)',data))).decode(),sep=' ').reshape(-1,3)
        v,f=np.unique(raw,axis=0,return_inverse=True);f=f.reshape(-1,3)
        bounds=np.array([v.min(0),v.max(0)])
        # Native X lateral, Y superior, Z anterior. Horizontal slices.
        slices=[]
        for h in np.arange(0,91,5):
            tri=v[f]
            hits=[]
            for a,b in [(0,1),(1,2),(2,0)]:
                pa,pb=tri[:,a],tri[:,b]
                active=((pa[:,1]<=h)&(pb[:,1]>h))|((pb[:,1]<=h)&(pa[:,1]>h))
                aa,bb=pa[active],pb[active]
                q=aa+(bb-aa)*((h-aa[:,1])/(bb[:,1]-aa[:,1]))[:,None]
                hits.append(q[:,[0,2]])
            pts=np.vstack(hits)
            if len(pts)>3:
                hu=ConvexHull(pts)
                p=pts[hu.vertices]
                per=np.linalg.norm(p-np.roll(p,1,axis=0),axis=1).sum()
                slices.append({'native_y_mm':float(h),'convex_section_perimeter_mm':float(per),'width_mm':float(np.ptp(pts[:,0])),'depth_mm':float(np.ptp(pts[:,1]))})
        # Report superior vertex in true ear regions, manually constrained to avoid scalp.
        ears=[]
        for side in [-1,1]:
            region=v[(side*v[:,0]>bounds[1,0]*.82)&(v[:,1]>-40)&(v[:,1]<45)&(v[:,2]<20)]
            pt=region[region[:,1].argmax()]
            ears.append(pt.tolist())
        center=v[np.abs(v[:,0])<.25]
        # center sagittal anterior profile, binned at 1 mm superior-coordinate bands
        nose=[]
        for h in np.arange(-30,51,2):
            q=center[np.abs(center[:,1]-h)<1]
            if len(q):nose.append({'native_y_mm':float(h),'anterior_xyz_mm':q[q[:,2].argmax()].tolist()})
        REPORT[size]={'file':name,'vertices':len(v),'triangles':len(f),'native_bounds_mm':bounds.tolist(),'native_size_mm':(bounds[1]-bounds[0]).tolist(),'horizontal_convex_sections':slices,'ear_superior_region_vertices_xyz_mm':ears,'sagittal_nose_profile':nose}
        if size=='small':
            (HERE/'Small_Symmetry.stl').write_bytes(data)
            np.savez_compressed(HERE/'Small_Symmetry.npz',v=v,f=f)
(HERE/'headform_measurements.json').write_text(json.dumps(REPORT,indent=2),encoding='utf-8')
for size,r in REPORT.items():
    near=min(r['horizontal_convex_sections'],key=lambda a:abs(a['convex_section_perimeter_mm']-560))
    print(size,'size',r['native_size_mm'],'near560',near,'ears',r['ear_superior_region_vertices_xyz_mm'])
