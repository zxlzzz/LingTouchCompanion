"""Re-read optical axes and diffuser faces from original STEP, no geometry edits."""
from pathlib import Path
import hashlib,json,math,sys
import numpy as np
from OCP.STEPCAFControl import STEPCAFControl_Reader
from OCP.TDocStd import TDocStd_Document
from OCP.TCollection import TCollection_ExtendedString
from OCP.XCAFDoc import XCAFDoc_DocumentTool
from OCP.TDF import TDF_Label
try:
    from OCP.TDF import TDF_LabelSequence
except ImportError:
    from OCP.collections import Sequence_TDF_Label as TDF_LabelSequence
from OCP.TDataStd import TDataStd_Name
from OCP.TopLoc import TopLoc_Location
from OCP.TopExp import TopExp_Explorer
from OCP.TopAbs import TopAbs_FACE,TopAbs_EDGE
from OCP.TopoDS import TopoDS
from OCP.BRepAdaptor import BRepAdaptor_Surface,BRepAdaptor_Curve
from OCP.GeomAbs import GeomAbs_Cylinder,GeomAbs_Circle,GeomAbs_Plane
from OCP.Bnd import Bnd_Box
from OCP.BRepBndLib import BRepBndLib
from OCP.BRepGProp import BRepGProp
from OCP.GProp import GProp_GProps
from OCP.IFSelect import IFSelect_RetDone

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
SOURCE=ROOT/'glasses_refs/cs30_radxa/CS30_official.stp'
def xyz(p):return [p.X(),p.Y(),p.Z()]
def bounds(shape):
    b=Bnd_Box();BRepBndLib.AddOptimal_s(shape,b,False,False)
    if b.IsVoid():return None
    return xyz(b.CornerMin())+xyz(b.CornerMax())
def name(label):
    a=TDataStd_Name()
    return a.Get().ToExtString() if label.FindAttribute(TDataStd_Name.GetID_s(),a) else ''
def optical_features(shape):
    faces=[];circles=[];ex=TopExp_Explorer(shape,TopAbs_FACE);i=0
    while ex.More():
        face=TopoDS.Face(ex.Current());s=BRepAdaptor_Surface(face,True);row={'face_index_within_leaf':i,'bounds_xyz_mm':bounds(face)}
        if s.GetType()==GeomAbs_Cylinder:
            c=s.Cylinder();row.update(type='cylinder',radius_mm=c.Radius(),axis_point_xyz_mm=xyz(c.Axis().Location()),axis_direction=xyz(c.Axis().Direction()));faces.append(row)
        elif s.GetType()==GeomAbs_Plane:
            p=s.Plane();prop=GProp_GProps();BRepGProp.SurfaceProperties_s(face,prop)
            row.update(type='plane',plane_point_xyz_mm=xyz(p.Location()),normal=xyz(p.Axis().Direction()),area_mm2=prop.Mass(),area_centroid_xyz_mm=xyz(prop.CentreOfMass()));faces.append(row)
        ex.Next();i+=1
    ex=TopExp_Explorer(shape,TopAbs_EDGE);i=0
    while ex.More():
        edge=TopoDS.Edge(ex.Current());c=BRepAdaptor_Curve(edge)
        if c.GetType()==GeomAbs_Circle:
            a=c.Circle();circles.append({'edge_index_within_leaf':i,'radius_mm':a.Radius(),'center_xyz_mm':xyz(a.Location()),'axis_direction':xyz(a.Axis().Direction()),'bounds_xyz_mm':bounds(edge)})
        ex.Next();i+=1
    return faces,circles

def main():
    reader=STEPCAFControl_Reader();reader.SetNameMode(True);reader.SetColorMode(False)
    assert reader.ReadFile(str(SOURCE))==IFSelect_RetDone
    document=TDocStd_Document(TCollection_ExtendedString('MDTV-XCAF'));assert reader.Transfer(document)
    tool=XCAFDoc_DocumentTool.ShapeTool_s(document.Main());roots=TDF_LabelSequence();tool.GetFreeShapes(roots)
    leaves=[];selected=[]
    def walk(label,location,parents):
        nm=name(label)
        if tool.IsReference_s(label):
            referred=TDF_Label();tool.GetReferredShape_s(label,referred)
            walk(referred,location.Multiplied(tool.GetLocation_s(label)),parents+[nm]);return
        components=TDF_LabelSequence()
        if tool.GetComponents_s(label,components,False):
            for j in range(1,components.Length()+1):walk(components.Value(j),location,parents+[nm])
            return
        shape=tool.GetShape_s(label).Moved(location)
        if shape.IsNull():return
        box=bounds(shape)
        if box is None:return
        leaf={'leaf_index':len(leaves),'name':nm,'parents':parents,'bounds_xyz_mm':box};leaves.append(leaf)
        role=None
        if '01-2-JINGTOU_' in parents and nm=='SOLID':role='RGB camera lens'
        if 'L061A-0_LENS_SPEC_V04_20200113' in parents and nm=='SOLID':role='ToF receiver lens'
        if nm=='DIFUSSER_4_2_1':role='VCSEL transmitter diffuser'
        if role:
            rows,circles=optical_features(shape);selected.append({**leaf,'role':role,'faces':rows,'circle_edges':circles})
    for j in range(1,roots.Length()+1):walk(roots.Value(j),TopLoc_Location(),[])
    assert len(selected)==3,len(selected)
    centers=[]
    for leaf in selected:
        if 'diffuser' in leaf['role']:
            top=max([f for f in leaf['faces'] if f['type']=='plane' and abs(f['normal'][2])>.999],key=lambda f:f['area_centroid_xyz_mm'][2])
            center=top['area_centroid_xyz_mm'];method='Exact area centroid of actual front planar diffuser face; no schematic point.'
            evidence={'face_index_within_leaf':top['face_index_within_leaf'],'front_face_area_mm2':top['area_mm2'],'front_face_bounds_xyz_mm':top['bounds_xyz_mm'],'front_face_normal':top['normal']}
        else:
            axial=[f for f in leaf['faces'] if f['type']=='cylinder' and abs(f['axis_direction'][2])>.999 and f['radius_mm']>2]
            # The optical axis is corroborated by multiple actual coaxial
            # cylinder faces and front circular edges within named lens part.
            assert axial,leaf['role']
            groups={}
            for feature in axial:groups.setdefault(tuple(np.round(feature['axis_point_xyz_mm'][:2],8)),[]).append(feature)
            optical_group=max(groups,key=lambda key:len(groups[key]));coaxial=groups[optical_group]
            cx=np.array([f['axis_point_xyz_mm'][:2] for f in coaxial]);center=[float(np.median(cx[:,0])),float(np.median(cx[:,1])),max(f['bounds_xyz_mm'][5] for f in coaxial)]
            method='Measured axes of actual cylindrical lens surfaces, corroborated by circular edges; Z is representative outer front cylinder height, not optical principal plane.'
            corroborating=[f for f in leaf['circle_edges'] if f['radius_mm']>2 and abs(f['axis_direction'][2])>.999 and np.linalg.norm(np.array(f['center_xyz_mm'][:2])-np.array(center[:2]))<1e-7]
            evidence={'axial_cylinder_faces':coaxial,'coaxial_circle_edges':corroborating,'axis_xy_spread_mm':(cx.max(0)-cx.min(0)).tolist(),'excluded_off_axis_cylinder_count':len(axial)-len(coaxial),'identification':'Named physical lens; dominant repeated coaxial cylinder group, corroborated by matching circular-edge centers. Other displaced cylinders are local lens-holder details and are excluded.'}
        centers.append({'role':leaf['role'],'leaf_index':leaf['leaf_index'],'local_step_center_xyz_mm':center,'reliable_native_front_projection_x_y_mm':center[:2],'reference_z_interpretation':'Actual diffuser front-face centroidZ for transmitter; lens cylinder feature referenceZ for receivers. Lens principal plane and complete-case front-plane registration are not identified.','measurement_method':method,'evidence':evidence})
    centers.sort(key=lambda r:r['local_step_center_xyz_mm'][0])
    # Stadium inner window spansX±34, vertical±10 about the face center.
    # Straight horizontal center segment isX±24, radius10; signed point
    # clearance=10-distance to that center segment.
    for row in centers:
        x,y,z=row['local_step_center_xyz_mm'];capsule_distance=math.hypot(max(abs(x)-24,0),y);clearance=10-capsule_distance
        row.update(conditional_full_face_center_x_h_mm=[x,15+y],conditional_inner_window_clearance_mm=clearance,conditional_ge8_pass=clearance>=8)
    global_bounds=[np.min(np.array([a['bounds_xyz_mm'][:3] for a in leaves]),axis=0).tolist(),np.max(np.array([a['bounds_xyz_mm'][3:] for a in leaves]),axis=0).tolist()]
    report={'source_step':str(SOURCE),'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),'step_reparsed_with_OCP':True,'step_leaf_count':len(leaves),'step_all_geometry_bounds_xyz_mm':global_bounds,'centers':centers,'window_inner_width_height_mm':[68,20],'window_center_on_nominal_full_face_x_h_mm':[0,15],'window_inner_radius_mm':10,'window_inner_straight_center_segment_x_mm':[-24,24],'wall_thickness_mm':2,'chamfer_angle_deg':45,'window_outer_width_height_mm':[72,24],'registration_assumption':'Native STEP X=0,Y=0 optical baseline aligned to complete89.94x30x25 camera front-face center. NativeY becomes face height offset from15. This alignment is an explicit assumption, not a measured registration. Optical axis parallel to window normal; projection along axis does not changeX/Y.','complete_camera_front_face_registration_status':'没查: STEP internal/module/FOV geometry has no identified complete89.94x30x25 enclosure datums; supplied dimensions drawing gives overall envelope but does not establish STEP-to-case origin correspondence.','actual_as_installed_three_center_clearance_mm':'没查','actual_as_installed_ge8_pass':'没查','conditional_min_clearance_mm':min(r['conditional_inner_window_clearance_mm'] for r in centers),'conditional_all_ge8_pass':all(r['conditional_ge8_pass'] for r in centers),'minimum_center_margin_requirement_mm':8,'conditional_required_window_height_at_width68_mm':2*(8+max(abs(r['local_step_center_xyz_mm'][1]) for r in centers)),'limitations':'Center margins only, as requested; clearances of optical aperture rims, angular field-of-view vignetting, actual complete-case registration, and camera seating repeatability are not measured here. The chamfer enlarges the outside edge; inner68x20 opening controls center margin. No enclosure model is changed.'}
    (HERE/'optics_audit.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='centers'},indent=2,ensure_ascii=False))
    print(json.dumps([{'role':r['role'],'local_step_center_xyz_mm':r['local_step_center_xyz_mm'],'conditional_clearance_mm':r['conditional_inner_window_clearance_mm']} for r in centers],indent=2))

if __name__=='__main__':main()
