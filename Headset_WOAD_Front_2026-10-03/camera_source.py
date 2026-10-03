"""Rebuild unchanged physical camera reference triangles from the customer STEP.

Run with the same Python/OCP geometry runtime as build.py. This is a source
converter, not an enclosure generator. Part paths are checked before use, and
only three optical simulation bodies are excluded. The real front glass face
receives a separate material ID without moving or inventing its triangles.
"""
from pathlib import Path
import hashlib,json
import numpy as np
from OCP.STEPControl import STEPControl_Reader
from OCP.IFSelect import IFSelect_RetDone
from OCP.TopoDS import TopoDS,TopoDS_Iterator
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE,TopAbs_REVERSED
from OCP.BRepMesh import BRepMesh_IncrementalMesh
from OCP.BRep import BRep_Tool
from OCP.TopLoc import TopLoc_Location
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib

P=Path(__file__).resolve().parent
SOURCE=P.parent/'Headset_Repro/raw/CS30_customer.stp'
INPUT=P/'inputs'
EXCLUDED_FOV_PARTS={23,62,63}
def children(shape):
    it=TopoDS_Iterator(shape);out=[]
    while it.More():out.append(it.Value());it.Next()
    return out
def bounds(shape):
    box=Bnd_Box();BRepBndLib.AddOptimal_s(shape,box,False,False)
    a,b=box.CornerMin(),box.CornerMax()
    return [a.X(),a.Y(),a.Z(),b.X(),b.Y(),b.Z()]
def tessellate(shape):
    BRepMesh_IncrementalMesh(shape,.035,False,.13,True).Perform()
    v=[];f=[];ex=TopExp_Explorer(shape,TopAbs_FACE)
    while ex.More():
        face=TopoDS.Face(ex.Current());loc=TopLoc_Location()
        tri=BRep_Tool.Triangulation_s(face,loc)
        if tri is not None:
            off=len(v);tf=loc.Transformation()
            for i in range(1,tri.NbNodes()+1):
                p=tri.Node(i).Transformed(tf);v.append([p.X(),p.Y(),p.Z()])
            for i in range(1,tri.NbTriangles()+1):
                a,b,c=tri.Triangle(i).Get();row=[off+a-1,off+b-1,off+c-1]
                f.append(row[::-1] if face.Orientation()==TopAbs_REVERSED else row)
        ex.Next()
    return np.array(v),np.array(f,dtype=np.int32)
def array_digest(a):
    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()
def main():
    reader=STEPControl_Reader();assert reader.ReadFile(str(SOURCE))==IFSelect_RetDone
    assert reader.TransferRoots()>0
    parts=[part for top in children(reader.OneShape()) for part in children(top)]
    assert len(parts)==124,f'Unexpected STEP hierarchy: {len(parts)} parts'
    housing_bounds=bounds(parts[123]);size=np.array(housing_bounds[3:])-housing_bounds[:3]
    assert np.allclose(size,[89.941993,30.000314,25],atol=.001),size
    assert np.allclose(bounds(parts[0])[:2],[-28.5,-6.5],atol=.001)
    assert np.allclose(bounds(parts[1])[:2],[14.9,-7.1],atol=.001)
    assert np.allclose(bounds(parts[2])[-1],-1,atol=.001)
    vv=[];ff=[];material=[];off=0;part_rows=[]
    # Tessellate in the original part order, including the virtual bodies before
    # exclusion, so shared source tessellation follows the original converter.
    for i,part in enumerate(parts):
        v,f=tessellate(part)
        part_rows.append({'id':i,'bounds_native_xyz_mm':bounds(part),'excluded_fov':i in EXCLUDED_FOV_PARTS,'triangle_count':len(f)})
        if i in EXCLUDED_FOV_PARTS or not len(f):continue
        vv.append(v);ff.append(f+off);material.append(np.full(len(f),i));off+=len(v)
    v=np.concatenate(vv);f=np.concatenate(ff);pid=np.concatenate(material)
    tri=v[f]
    # This is the real planar cover-glass face at native Z=0: capsule83×17.8,
    # centered atX±32.5, radius8.9. Adjacent opaque rim remains housing ID123.
    rad=np.hypot(np.maximum(np.abs(tri[:,:,0])-32.5,0),tri[:,:,1])
    glass=(pid==123)&(np.max(np.abs(tri[:,:,2]),axis=1)<1e-6)&(np.max(rad,axis=1)<8.900001)
    pid[glass]=124
    INPUT.mkdir(exist_ok=True)
    arrays={'v':v,'f':f,'part':pid}
    np.savez_compressed(INPUT/'camera_physical_native.npz',**arrays)
    opt=(pid>=0)&(pid<=3)
    np.savez_compressed(INPUT/'camera_optics_native.npz',v=v,f=f[opt],part=pid[opt])
    materials={str(i):('lens' if i<=3 else 'metal' if i in [120,121] else 'camera_glass' if i==124 else 'camera') for i in np.unique(pid)}
    (INPUT/'camera_materials.json').write_text(json.dumps(materials,indent=2),encoding='utf8')
    provenance={'source':'Headset_Repro/raw/CS30_customer.stp','source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                'housing_immediate_path':[1,115],'housing_part_id':123,'housing_bounds_native_xyz_mm':housing_bounds,
                'excluded_fov_part_ids':sorted(EXCLUDED_FOV_PARTS),'material_only_split_glass_id':124,
                'linear_deflection_mm':.035,'angular_deflection_radians':.13,
                'array_sha256':{key:array_digest(a) for key,a in arrays.items()},'part_inventory':part_rows,
                'limitations':'Native source is an open STEP shell. This converter preserves all physical facets and does not synthesize a closed camera box or fill its source holes.'}
    (INPUT/'camera_source_provenance.json').write_text(json.dumps(provenance,indent=2),encoding='utf8')
    print(json.dumps({key:provenance[key] for key in ['source_sha256','housing_part_id','excluded_fov_part_ids','array_sha256']},indent=2))
if __name__=='__main__':main()
