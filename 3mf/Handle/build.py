"""Recover both manual handle meshes exactly; expose a future editing entry."""
import hashlib
import json
import numpy as np
import manifold3d as md
from source import P, SOURCE, read_source, apply


def modify_part(name, vertices, triangles):
    """Edit housing or cover in its original native mesh coordinates (mm).

    Preserve the native frame; the original component/build transforms are
    reapplied for printing. Default keeps every original vertex and triangle.
    """
    return vertices, triangles


def inspect(v, f):
    assert v.ndim==2 and v.shape[1]==3 and np.isfinite(v).all()
    assert f.ndim==2 and f.shape[1]==3 and np.issubdtype(f.dtype,np.integer)
    assert f.min()>=0 and f.max()<len(v)
    solid=md.Manifold(md.Mesh64(vert_properties=np.ascontiguousarray(v,dtype=np.float64),
                              tri_verts=np.ascontiguousarray(f,dtype=np.uint64)))
    assert solid.status()==md.Error.NoError and solid.volume()>0
    edges=np.sort(np.concatenate([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]]),axis=1)
    unused,counts=np.unique(edges,axis=0,return_counts=True)
    assert (counts==2).all(), 'Mesh has nonmanifold edges'
    return {'vertices':len(v),'triangles':len(f),'closed_manifold':True,
            'solid_components':len(solid.decompose()),'volume_mm3':float(solid.volume()),
            'native_bounds_xyz_mm':[v.min(0).tolist(),v.max(0).tolist()]}


def main():
    folder=P/'geometry';folder.mkdir(exist_ok=True)
    (P/'checks').mkdir(exist_ok=True)
    rows,unused=read_source()
    report={'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'parts':[]}
    for row in rows:
        v,f=modify_part(row['name'],row['v'].copy(),row['f'].copy())
        v,f=np.asarray(v,dtype=np.float64),np.asarray(f)
        info=inspect(v,f)
        posed=apply(v,row['native_to_print'])
        np.savez_compressed(folder/(row['name']+'.npz'),v=v,f=f)
        np.savez_compressed(folder/(row['name']+'_print.npz'),v=posed,f=f)
        info.update(name=row['name'],model_entry=row['model_entry'],mesh_object_id=row['mesh_object_id'],
                    build_object_id=row['build_object_id'],component_transform=row['component_transform'].tolist(),
                    build_transform=row['build_transform'].tolist(),print_bounds_xyz_mm=[posed.min(0).tolist(),posed.max(0).tolist()],
                    unchanged_source_mesh=np.array_equal(v,row['v']) and np.array_equal(f,row['f']))
        report['parts'].append(info)
    report['scope']='Exact two model objects, including all constituent solids. No new cut, welding, remeshing or inferred CAD history.'
    (folder/'geometry_values.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
