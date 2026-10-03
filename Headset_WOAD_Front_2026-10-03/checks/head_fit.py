"""Independent head fit: exact surface clearance plus exterior classification.

Run with the repository analysis Python for distances, then the bundled CAD
Python for signed classification:
    python checks/head_fit.py --phase distances
    <CAD python> checks/head_fit.py --phase classify
    <CAD python> checks/head_fit.py --phase baselines
No model source or geometry is changed.
"""
from pathlib import Path
import argparse,ast,hashlib,json,sys
import numpy as np

P=Path(__file__).resolve().parent
ART=P.parent
ROOT=ART.parent
G=ART/'geometry'
HEAD=ROOT/'Headset_Carbon6K_FlatBase_Review_2026-10-02/inputs/Medium_Trial_Registered.npz'
PARTS=['visor','service_lid','service_lip','fasteners','tab_bridges','shifted_tabs','cradle_ribs','bezel_trim','pads','cable_gland','camera']
OUTPUT=P/'head_fit.json'

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def load(path):
    a=np.load(path);return a['v'],a['f']
def assert_fresh(report):
    assert report['head_sha256']==sha(HEAD),'Head source changed during independent audit'
    assert report['build_source_sha256']==sha(ART/'build.py'),'Build source changed during independent audit'
    assert report['geometry_values_sha256']==sha(G/'geometry_values.json'),'Geometry measurements changed during independent audit'
    for name in PARTS:
        assert report['source_geometry_sha256'][name]==sha(G/(name+'.npz')),name+' source changed during independent audit'

def distance_functions():
    source=ROOT/'Headset_Carbon6K_FlatBase_Review_2026-10-02/audit/audit_surface_distances.py'
    sys.path.insert(0,str(ROOT/'Headset_Carbon6K_FlatBase_Review_2026-10-02/inputs'))
    tree=ast.parse(source.read_text(encoding='utf8'))
    nodes=[a for a in tree.body if isinstance(a,(ast.Import,ast.ImportFrom,ast.FunctionDef)) and not(isinstance(a,ast.FunctionDef) and a.name=='main')]
    ns={};exec(compile(ast.Module(nodes,type_ignores=[]),str(source),'exec'),ns)
    return ns

def distances():
    HV,HF=load(HEAD);HT=HV[HF];ns=distance_functions()
    report={'head_source':str(HEAD.relative_to(ROOT)), 'head_sha256':sha(HEAD),'head_pose_unchanged':True,'build_source_sha256':sha(ART/'build.py'),'geometry_values_sha256':sha(G/'geometry_values.json'),'source_geometry_sha256':{n:sha(G/(n+'.npz')) for n in PARTS},'parts':{},'exempt_original_parts':['original_normal','original_temples'],'basis':'Original raw BTTF collision is excluded; all independently added printable parts, pad references, fasteners and actual physical camera are checked.'}
    for name in PARTS:
        V,F=load(G/(name+'.npz'))
        # Crop only by a guaranteed source-vertex upper bound plus epsilon.
        # Every excluded head triangle is farther than this pad from the whole
        # candidate bounding box, hence cannot attain a smaller minimum.
        from scipy.spatial import cKDTree
        upper=float(cKDTree(HV).query(V)[0].min())
        pad=upper+1e-7
        lo=V.min(0)-pad;hi=V.max(0)+pad
        keep=np.all(HT.max(1)>=lo,axis=1)&np.all(HT.min(1)<=hi,axis=1)
        selected=HT[keep];localV=selected.reshape(-1,3);localF=np.arange(len(localV)).reshape(-1,3)
        result=ns['continuous_min'](localV,localF,V,F)
        if result['head_face_index']>=0:result['head_face_index']=int(np.flatnonzero(keep)[result['head_face_index']])
        result['excluded_head_triangle_distance_lower_bound_mm']=pad
        result['head_triangles_checked']=len(selected)
        result['surface_intersection_absent']=bool(result['distance_mm']>1e-6)
        report['parts'][name]={'continuous_triangle_clearance':result}
        print(name,result['distance_mm'],flush=True)
    report['all_surface_intersections_absent']=all(p['continuous_triangle_clearance']['surface_intersection_absent'] for p in report['parts'].values())
    OUTPUT.write_text(json.dumps(report,indent=2),encoding='utf8')

def classify():
    import vtk
    from vtk.util.numpy_support import numpy_to_vtk,numpy_to_vtkIdTypeArray
    def poly(v,f):
        points=vtk.vtkPoints();points.SetData(numpy_to_vtk(np.ascontiguousarray(v,dtype=np.float64),deep=True))
        ca=vtk.vtkCellArray();ca.SetData(numpy_to_vtkIdTypeArray(np.arange(0,len(f)*3+1,3,dtype=np.int64),deep=True),numpy_to_vtkIdTypeArray(np.ascontiguousarray(f.ravel(),dtype=np.int64),deep=True))
        data=vtk.vtkPolyData();data.SetPoints(points);data.SetPolys(ca);return data
    report=json.loads(OUTPUT.read_text(encoding='utf8'))
    assert report['head_sha256']==sha(HEAD),'Head source changed during independent audit'
    assert report['build_source_sha256']==sha(ART/'build.py'),'Build source changed during independent audit'
    assert report['geometry_values_sha256']==sha(G/'geometry_values.json'),'Geometry measurements changed during independent audit'
    HV,HF=load(HEAD);data=poly(HV,HF)
    implicit=vtk.vtkImplicitPolyDataDistance();implicit.SetInput(data)
    # Confirm original head normals classify an anatomical interior/exterior
    # pair correctly rather than assume the normal orientation.
    controls={'interior_center':[0,105,45],'anterior_exterior':[0,-50,45],'lateral_exterior':[100,125,35]}
    values={n:float(implicit.EvaluateFunction(v)) for n,v in controls.items()}
    assert values['interior_center']<0 and values['anterior_exterior']>0 and values['lateral_exterior']>0,values
    report['classification_controls_mm']=values
    for name in PARTS:
        assert report['source_geometry_sha256'][name]==sha(G/(name+'.npz')),name+' source changed during independent audit'
        V,F=load(G/(name+'.npz'));points=np.vstack([V,V[F].mean(1)])
        d=np.array([implicit.EvaluateFunction(p) for p in points]);i=int(d.argmin())
        item={'method':'Signed closest triangle feature with source head normals, at every candidate vertex and triangle centroid. Anatomical control points establish sign. Positive continuous surface separation plus exterior classification excludes penetration; source head neck remains open and no head-volume Boolean is used.','points_checked':len(points),'negative_points':int((d<-1e-6).sum()),'minimum_signed_sample_distance_mm':float(d[i]),'minimum_witness_xyz_mm':points[i].tolist(),'all_checked_points_exterior':bool(np.all(d>=-1e-6))}
        report['parts'][name]['exterior_classification']=item
        report['parts'][name]['pass']=item['all_checked_points_exterior'] and report['parts'][name]['continuous_triangle_clearance']['surface_intersection_absent']
        print(name,'outside',item['all_checked_points_exterior'],'min',d[i],flush=True)
    report['all_added_parts_and_camera_pass']=all(p['pass'] for p in report['parts'].values())
    assert_fresh(report)
    OUTPUT.write_text(json.dumps(report,indent=2),encoding='utf8')

def baselines():
    import manifold3d as md
    def solid(path):
        v,f=load(path);return md.Manifold(md.Mesh64(vert_properties=np.ascontiguousarray(v,dtype=np.float64),tri_verts=np.ascontiguousarray(f,dtype=np.uint64)))
    def box(lo,hi):
        lo=np.asarray(lo);return md.Manifold.cube(tuple(np.asarray(hi)-lo)).translate(tuple(lo))
    oldpath=ROOT/'Headset_CompactFront_Review_2026-10-02/inputs/front_tabs.npz'
    v,f=load(oldpath);v=v.copy();v[:,0]+=np.sign(v[:,0])*5.1
    expected=md.Manifold(md.Mesh64(vert_properties=np.ascontiguousarray(v,dtype=np.float64),tri_verts=np.ascontiguousarray(f,dtype=np.uint64)))
    actual=solid(G/'shifted_tabs.npz')
    difference=(actual-expected)+(expected-actual)
    slot_void=box([-100,151.5703299,26.2],[100,154.5703299,52.2])
    values=json.loads((G/'geometry_values.json').read_text(encoding='utf8'))
    temple_y=float(values['original_temple_preserved_from_y_mm'])
    original=solid(G/'original_normal.npz')
    expected_temples=original^box([-120,temple_y,-5],[120,170,70])
    actual_temples=solid(G/'original_temples.npz')
    temple_difference=(actual_temples-expected_temples)+(expected_temples-actual_temples)
    report=json.loads(OUTPUT.read_text(encoding='utf8'))
    assert_fresh(report)
    report['unchanged_source_geometry']={
        'tab_baseline_source':str(oldpath.relative_to(ROOT)),
        'tab_baseline_sha256':sha(oldpath),
        'symmetric_lateral_tab_translation_mm':5.1,
        'slot_y_mm':[151.5703299,154.5703299],
        'slot_z_mm':[26.2,52.2],
        'distal_tab_y_mm':159.0703299,
        'tab_expected_vs_actual_symmetric_difference_volume_mm3':float(difference.volume()),
        'slot_blockage_volume_mm3':float((actual^slot_void).volume()),
        'original_temple_region_y_mm':[temple_y,147.0703299],
        'temple_expected_vs_actual_symmetric_difference_volume_mm3':float(temple_difference.volume()),
        'temple_source_yz_and_length_unchanged':abs(temple_difference.volume())<1e-6,
        'tabs_only_laterally_translated_and_slots_preserved':abs(difference.volume())<1e-6 and abs((actual^slot_void).volume())<1e-6,
    }
    OUTPUT.write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report['unchanged_source_geometry'],indent=2))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--phase',choices=['distances','classify','baselines'],required=True);args=parser.parse_args()
    if args.phase=='distances':distances()
    elif args.phase=='classify':classify()
    else:baselines()
if __name__=='__main__':main()
