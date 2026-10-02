from pathlib import Path
import numpy as np,json
from triangle_distance import min_triangle_distance,clip_triangles_y_negative
P=Path(__file__).resolve().parent
q=np.load(P/'Medium_Trial_Registered.npz');v,f=q['v'],q['f'];tri=v[f]
sel=(np.abs(tri[:,:,0]).max(1)<30)&(tri[:,:,1].min(1)<12)&(tri[:,:,2].max(1)>-10)&(tri[:,:,2].min(1)<45)
ids=np.flatnonzero(sel);H=tri[sel]
a=np.deg2rad(20);s,c=np.sin(a),np.cos(a);O=np.array([0,-.8,23.6]);UP=np.array([0,-s,c]);FW=np.array([0,-c,-s])
def yz(q,t):return O+q*UP+t*FW
front_bottom_y=-.8-(25+s*(0-23.6))/c
roof_y0_z=23.6+(-2.5+s*.8)/c
roof_front=yz(-2.5,25)
def lower_surfaces(halfwidth):
    surfaces=[];names=[]
    def quad(points,name):
        surfaces.extend([[points[0],points[1],points[2]],[points[0],points[2],points[3]]]);names.extend([name,name])
    for sign in [-1,1]:
        x=sign*halfwidth
        quad([[x,0,0],[x,front_bottom_y,0],[x,roof_front[1],roof_front[2]],[x,0,roof_y0_z]],'nose_channel_side_'+str(sign))
        quad([[x,0,0],[sign*47.3,0,0],[sign*47.3,front_bottom_y,0],[x,front_bottom_y,0]],'outer_wing_bottom_'+str(sign))
    quad([[-halfwidth,0,roof_y0_z],[halfwidth,0,roof_y0_z],[halfwidth,roof_front[1],roof_front[2]],[-halfwidth,roof_front[1],roof_front[2]]],'central_channel_roof')
    return np.array(surfaces),names
C,names=lower_surfaces(13);answer=min_triangle_distance(H,C)
report={'scope':'Analytic newly added Y<0 lower case surfaces only: channel roof, channel sides, outer wing bottoms. Full actual case mesh validation remains pending.',
 'nose_distance_mm':answer[0],'nose_xyz_mm':answer[1].tolist(),'case_xyz_mm':answer[2].tolist(),'head_triangle_index':int(ids[answer[3]]),'case_analytic_triangle_index':answer[4],'case_feature':names[answer[4]],
 'method':'Continuous triangle-triangle distance from original head surface, testing vertex-face, interior edge-edge, segment-face intersections. Y0 boundary is limit of Y<0 lower surfaces, not an included back plane.',
 'meets_2mm':answer[0]>=2,'head_trial_only':True}
strict,strict_ids=clip_triangles_y_negative(C.reshape(-1,3),np.arange(C.size//3).reshape(-1,3),limit=-1e-6)
sa=min_triangle_distance(H,strict)
report['strict_y_limit_mm']=-1e-6
report['strict_y_distance_mm']=sa[0]
report['strict_y_nose_xyz_mm']=sa[1].tolist()
report['strict_y_case_xyz_mm']=sa[2].tolist()
(P/'analytic_case_nose_distance.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
np.savez_compressed(P/'analytic_lower_case_triangles.npz',triangles=C)
print(json.dumps(report,indent=2))
width_checks=[]
for halfwidth in [13.5,14.,14.5,15.]:
    ca,nn=lower_surfaces(halfwidth);aa=min_triangle_distance(H,ca)
    width_checks.append({'halfwidth_mm':halfwidth,'total_channel_width_mm':2*halfwidth,'nose_gap_mm':aa[0],'nose_xyz_mm':aa[1].tolist(),'case_xyz_mm':aa[2].tolist(),'feature':nn[aa[4]],'meets_2mm':aa[0]>=2})
(P/'channel_width_alternatives_analytic.json').write_text(json.dumps(width_checks,indent=2),encoding='utf-8')
print(json.dumps(width_checks,indent=2))
lo,hi=13.,14.5
for _ in range(40):
    mid=(lo+hi)/2;cc,_=lower_surfaces(mid)
    if min_triangle_distance(H,cc)[0]<2:lo=mid
    else:hi=mid
minimal,nn=lower_surfaces(hi);aa=min_triangle_distance(H,minimal)
lower_bound={'scope':'Analytic lower surfaces only; necessary candidate pending full-case surface check, not applied to case.',
 'minimum_channel_halfwidth_mm':hi,'minimum_total_channel_width_mm':2*hi,'distance_mm':aa[0],'nose_xyz_mm':aa[1].tolist(),'case_xyz_mm':aa[2].tolist(),'feature':nn[aa[4]],'numerical_bracket_mm':[lo,hi],'unchanged_camera':True}
(P/'channel_minimum_analytic.json').write_text(json.dumps(lower_bound,indent=2),encoding='utf-8')
print(json.dumps(lower_bound,indent=2))
