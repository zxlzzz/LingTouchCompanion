"""Audit the separately saved front against the actual head, camera and slots.

Only revised/checks/fit.json is retained. Existing audit code supplies the same
continuous triangle and signed-classification methods, with output redirected
to a temporary folder; previous checks and finished models are never changed.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import sys
import tempfile
import numpy as np
import manifold3d as md
import vtk
from vtk.util.numpy_support import numpy_to_vtk, numpy_to_vtkIdTypeArray

P = Path(__file__).resolve().parent
BASE = P.parent
ROOT = BASE.parent
G = P/'geometry'
C = P/'checks'
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path): return np.load(path)
def solid(q):
    m = md.Manifold(md.Mesh64(vert_properties=np.ascontiguousarray(q['v'],dtype=np.float64),
                              tri_verts=np.ascontiguousarray(q['f'],dtype=np.uint64)))
    assert m.status() == md.Error.NoError
    return m

def head_field(q):
    points = vtk.vtkPoints()
    points.SetData(numpy_to_vtk(np.ascontiguousarray(q['v'],dtype=np.float64),deep=True))
    faces = q['f']
    cells = vtk.vtkCellArray()
    cells.SetData(numpy_to_vtkIdTypeArray(np.arange(0,len(faces)*3+1,3,dtype=np.int64),deep=True),
                  numpy_to_vtkIdTypeArray(np.ascontiguousarray(faces.ravel(),dtype=np.int64),deep=True))
    data = vtk.vtkPolyData(); data.SetPoints(points); data.SetPolys(cells)
    field = vtk.vtkImplicitPolyDataDistance(); field.SetInput(data)
    return field

def main():
    C.mkdir(parents=True,exist_ok=True)
    values = json.loads((G/'geometry_values.json').read_text('utf8'))
    assert 'nose_support' in values, 'Revised nose support has not been built'
    sources = [P/'build.py',P/'verify.py',BASE/'build.py',BASE/'checks/head_fit.py',
               BASE/'checks/mesh_distance.py',G/'geometry_values.json',G/'front_body.npz',
               G/'nose_support.npz',G/'camera.npz',G/'retention_band.npz',
               ROOT/'Headset_Inputs/Medium_Trial_Registered.npz',ROOT/'Headset_Inputs/datums.json']
    source_hashes = {str(path.relative_to(ROOT)).replace('\\','/'):sha(path) for path in sources}
    sys.path.insert(0,str(BASE/'checks'))
    spec = importlib.util.spec_from_file_location('previous_head_audit_methods',BASE/'checks/head_fit.py')
    audit = importlib.util.module_from_spec(spec); spec.loader.exec_module(audit)
    audit.G = G
    with tempfile.TemporaryDirectory(prefix='fit_',dir=P) as temporary:
        audit.OUTPUT = Path(temporary)/'head_fit.json'
        previous = json.loads((BASE/'checks/head_fit.json').read_text('utf8'))
        # Contact pose is reusable only when both actual head and camera match.
        if previous.get('head_sha256') == sha(audit.HEAD) and previous.get('source_geometry_sha256',{}).get('camera') == sha(G/'camera.npz'):
            audit.OUTPUT.write_text(json.dumps(previous),encoding='utf8')
        audit.distances()
        audit.classify(.05)
        audit.slots()
        result = json.loads(audit.OUTPUT.read_text('utf8'))
    original_identity = {}
    for name in ['camera','retention_band']:
        old = read(BASE/'geometry'/(name+'.npz'))
        new = read(G/(name+'.npz'))
        identical = set(old.files) == set(new.files) and all(np.array_equal(old[key],new[key]) for key in old.files)
        assert identical, name+' changed'
        original_identity[name] = {'all_arrays_identical':identical,
            'old_sha256':sha(BASE/'geometry'/(name+'.npz')), 'revised_sha256':sha(G/(name+'.npz'))}
    bodyq = read(G/'front_body.npz'); body = solid(bodyq)
    f = bodyq['f']; edges = np.sort(np.concatenate([f[:,[0,1]],f[:,[1,2]],f[:,[2,0]]]),axis=1)
    _,counts = np.unique(edges,axis=0,return_counts=True)
    assert (counts==2).all() and len(body.decompose()) == 1
    camera = read(G/'camera.npz')
    hull = md.Manifold.hull_points(np.unique(np.round(camera['v'][np.unique(camera['f'])],8),axis=0))
    old_overlap = float((hull ^ solid(read(BASE/'geometry/front_body.npz'))).volume())
    new_overlap = float((hull ^ body).volume())
    nose = read(G/'nose_support.npz'); nose_body = solid(nose)
    nose_camera_overlap = float((hull ^ nose_body).volume())
    assert new_overlap <= old_overlap+1e-7 and new_overlap <= .001
    assert nose_camera_overlap < 1e-8
    tri = nose['v'][nose['f']]
    cross = np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
    areas = np.linalg.norm(cross,axis=1)/2
    normals = cross/(2*areas[:,None])
    field = head_field(read(audit.HEAD))
    centers = tri.mean(1)
    gaps = np.array([field.EvaluateFunction(p) for p in centers])
    # The +Y-facing side of the saddle faces the nasal skin. Its local outward
    # normal points toward the head; the head reaction is in the opposite way.
    contact = (normals[:,1]>.05)&(gaps>=-.05)&(gaps<=.06)
    assert contact.any(), 'No broad nose bearing surface near the head'
    bearing = tri[contact]; weights = areas[contact]
    reaction = -normals[contact]
    upward_area = float(np.sum(weights*np.maximum(reaction[:,2],0)))
    projected_area = float(np.sum(weights*normals[contact,1]))
    contact_points = bearing.reshape(-1,3)
    vertex_gaps = np.array([field.EvaluateFunction(p) for p in contact_points])
    bounds = [contact_points.min(0),contact_points.max(0)]
    nose_info = {
        'nose_source_sha256':sha(G/'nose_support.npz'),
        'whole_nose_piece_bounds_xyz_mm':[nose['v'].min(0).tolist(),nose['v'].max(0).tolist()],
        'nominal_width_mm':values['nose_support']['width_mm'],
        'nominal_height_mm':values['nose_support']['height_mm'],
        'head_facing_bearing_area_mm2':float(weights.sum()),
        'bearing_projected_xz_area_mm2':projected_area,
        'bearing_bounds_xyz_mm':[point.tolist() for point in bounds],
        'bearing_width_x_mm':float(bounds[1][0]-bounds[0][0]),
        'centroid_skin_gap_signed_range_mm':[float(gaps[contact].min()),float(gaps[contact].max())],
        'bearing_vertex_skin_gap_signed_range_mm':[float(vertex_gaps.min()),float(vertex_gaps.max())],
        'area_weighted_head_reaction_normal_xyz':np.average(reaction,axis=0,weights=weights).tolist(),
        'upward_reaction_projected_area_mm2':upward_area,
        'fraction_bearing_area_with_upward_normal':float(weights[reaction[:,2]>0].sum()/weights.sum()),
        'camera_bottom_to_nose_top_z_mm':float(camera['v'][:,2].min()-nose['v'][:,2].max()),
        'camera_conservative_hull_overlap_mm3':nose_camera_overlap,
        'method':'All +Y-facing saddle facets with signed head gap within 0.06 mm of nominal contact; actual triangle areas and outward normals. Negative gaps reported as sampled penetration, not hidden by a comfort stand-off.',
        'limitation':'Contact area and upward-facing reaction support geometric bearing; real wearing stability, comfort and retention are not physically certified.'
    }
    assert upward_area > 10 and projected_area > 100 and nose_info['bearing_width_x_mm'] > 20
    result['revision_build_source_sha256'] = sha(P/'build.py')
    result['unchanged_template_source_sha256'] = sha(BASE/'build.py')
    result['source_sha256'] = source_hashes
    result['nose_support'] = nose_info
    result['original_camera_and_band_identity'] = original_identity
    result['camera_body_overlap'] = {'old_conservative_hull_mm3':old_overlap,
        'revised_conservative_hull_mm3':new_overlap,'overlap_not_increased':new_overlap<=old_overlap+1e-7}
    result['body_manifold'] = {'closed_connected_manifold':True,'components':1,
        'volume_cm3':float(body.volume())/1000,'vertices':len(bodyq['v']),'triangles':len(f)}
    result['pass'] = bool(result['all_parts_sampled_penetration_within_contact_epsilon'] and
                          result['terminal_slots']['all_slot_locations_and_reach_preserved'] and
                          new_overlap<=.001 and upward_area>10)
    assert all(sha(ROOT/path)==value for path,value in source_hashes.items()), 'Sources changed during audit'
    (C/'fit.json').write_text(json.dumps(result,indent=2),encoding='utf8')
    print(json.dumps({'pass':result['pass'],'nose_support':nose_info,'camera_body_overlap':result['camera_body_overlap'],
                      'body_manifold':result['body_manifold']},indent=2),flush=True)
    assert result['pass'], 'Front audit failed; inspect revised/checks/fit.json'

if __name__ == '__main__':
    main()
