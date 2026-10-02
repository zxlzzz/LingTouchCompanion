"""First-stage placement review only. Dimensions in mm; no printable shell.

Camera-only revision, following the user's latest WOAD layout correction.
Run this file with numpy, matplotlib and scipy. Camera STEP measurements are
supplied alongside it. The supplied reference meshes are not modified.
World axes: X across the front, Y towards the back of the head, Z upwards.
"""
from pathlib import Path
import json
import math
import zipfile
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon
from scipy.interpolate import PchipInterpolator
from scipy.spatial import ConvexHull

HERE = Path(__file__).resolve().parent
plt.rcParams['font.family'] = 'Microsoft JhengHei'
plt.rcParams['axes.unicode_minus'] = False
CAM = '#df8a25'
BAT = '#8163af'
REF = '#84909e'
RES = '#3885c4'
theta = math.radians(20)
c, s = math.cos(theta), math.sin(theta)
# STEP axes: X across, Y up, Z optical forward.
R = np.array([[1,0,0],[0,-s,-c],[0,c,-s]])
camera_size = np.array([89.94,30.,25.])
camera_rotated_height = 30*c+25*s
camera_rotated_depth = 25*c+30*s
# Raise the original reviewed camera pose by exactly 2 mm in world Z.
camera_raise_mm = 2.
camera_center = np.array([0.,-camera_rotated_depth/2-1.5,
                          20.5+camera_rotated_height/2+camera_raise_mm])
camera_source_center = np.array([0.,0.,-12.5])

def corners(lo, hi):
    return np.array([[x,y,z] for x in [lo[0],hi[0]]
                     for y in [lo[1],hi[1]] for z in [lo[2],hi[2]]])

def camera_world(points):
    return (np.asarray(points)-camera_source_center)@R.T+camera_center

camera = camera_world(corners([-44.97,-15,-25],[44.97,15,0]))
camera_cavity = camera_world(corners([-45.47,-15.5,-25.5],[45.47,15.5,.5]))

# Depth budget only: tentative 3.5 mm world-Y front and rear wall reservations.
# These are dimension planes, not shell geometry. Optical cutaways are deferred.
front_wall_mm = rear_wall_mm = 3.5
cavity_front_y, cavity_rear_y = camera_cavity[:,1].min(), camera_cavity[:,1].max()
frame_front_y = cavity_front_y-front_wall_mm
frame_rear_y = cavity_rear_y+rear_wall_mm
frame_depth = frame_rear_y-frame_front_y
wing_end_y = 43.
whole_front_depth = wing_end_y-frame_front_y
battery_lo, battery_hi = np.array([-58.5,190.,4.]),np.array([58.5,205.,51.])
battery = corners(battery_lo,battery_hi)

# Port mouth is taken from the actual USB shell's STEP X-min, not its center.
camera_info = json.loads((HERE/'camera_step_measurements.json').read_text())
usb = next(row for row in camera_info['leaves'] if row['name']=='SHELL_0_60_1')
usb_bounds = np.array(usb['bounds'])
usb_mouth_source = np.array([usb_bounds[0],0.,(usb_bounds[2]+usb_bounds[5])/2])
usb_mouth = camera_world([usb_mouth_source])[0]
# Conservative bend space: 30 mm beyond the nominal complete-case envelope.
# The final case-to-STEP registration still requires verification.
usb_reserve = camera_world(corners([-74.97,-7,-25],[-44.97,7,-16]))
optical_sources = [(-22.,0.,-1.13),(7.,.005,-1.7),(22.,0.,-1.5581)]
optical_world = camera_world(optical_sources)

# Independently reconstructed reference outline: supplied measured anchors only.
curve_x = np.array([0.,50.,60.,65.,68.5,71.])
curve_y = np.array([0.,12.,19.,25.,33.,43.])
curve_fn = PchipInterpolator(curve_x,curve_y)
xx = np.linspace(0,71,160)
yy = curve_fn(xx)
front_curve = np.vstack([np.column_stack([-xx[::-1],yy[::-1]]),
                         np.column_stack([xx[1:],yy[1:]])])

def projected(points, view):
    if view=='front': return points[:,[0,2]]
    if view=='side': return points[:,[1,2]]
    return np.column_stack([points[:,0],-points[:,1]])

def hull(points, view):
    p = projected(points,view)
    return p[ConvexHull(p).vertices]

def shape(ax, points, view, color, alpha=.25, dashed=False, lw=1.6, zorder=3):
    poly = Polygon(hull(points,view),closed=True,facecolor=color,
                   edgecolor=color,alpha=alpha,linewidth=lw,
                   linestyle='--' if dashed else '-',zorder=zorder)
    ax.add_patch(poly)
    if alpha<.5:
        ax.add_patch(Polygon(hull(points,view),closed=True,fill=False,
                     edgecolor=color,linewidth=lw,
                     linestyle='--' if dashed else '-',zorder=zorder+1))

def note(ax,text,point,xytext,color='#253849'):
    ax.annotate(text,xy=point,xytext=xytext,fontsize=11,color=color,
                ha='left',va='center',
                arrowprops=dict(arrowstyle='-',color=color,lw=.9),
                bbox=dict(boxstyle='round,pad=.4',fc='white',ec='none',alpha=.9),zorder=20)

def dim(ax,a,b,text,offset=0,color='#566575'):
    a,b = np.array(a,float),np.array(b,float)
    d=b-a
    n=np.array([-d[1],d[0]])/np.linalg.norm(d)
    a2,b2=a+n*offset,b+n*offset
    ax.plot([a[0],a2[0]],[a[1],a2[1]],color=color,lw=.6)
    ax.plot([b[0],b2[0]],[b[1],b2[1]],color=color,lw=.6)
    ax.annotate('',xy=a2,xytext=b2,arrowprops=dict(arrowstyle='<->',color=color,lw=.9))
    mid=(a2+b2)/2
    ax.text(mid[0]+n[0]*2,mid[1]+n[1]*2,text,ha='center',va='bottom',
            fontsize=10,color=color,bbox=dict(fc='white',ec='none',pad=1),zorder=20)

def reference(ax,view):
    if view=='front':
        # Nose notch rounded at the top, 18 wide by 20 high.
        t=np.linspace(math.pi,0,40)
        notch=np.column_stack([9*np.cos(t),11+9*np.sin(t)])
        poly=np.vstack([[-71,55],[71,55],[71,0],[9,0],[9,11],
                        notch[::-1],[-9,11],[-9,0],[-71,0],[-71,55]])
        ax.plot(poly[:,0],poly[:,1],color=REF,lw=2,ls='--',zorder=1)
        dim(ax,[-71,55],[71,55],'参考宽 142',offset=17)
        dim(ax,[-71,0],[-71,55],'55',offset=11)
        dim(ax,[-9,0],[9,0],'鼻缺口 18',offset=-7)
    elif view=='side':
        bottom=PchipInterpolator([0,25,80,147],[0,5,36,36])(np.linspace(0,147,160))
        y=np.linspace(0,147,160)
        ax.plot(np.r_[y,y[::-1],0],np.r_[np.full_like(y,55),bottom[::-1],55],
                color=REF,lw=2,ls='--',zorder=1)
        dim(ax,[0,55],[147,55],'参考深 147',offset=14)
        # Connection scheme only, band thickness is not a printable part.
        ax.plot([147,190],[45.5,45.5],color='#627386',lw=8,alpha=.3,zorder=1)
        ax.plot([205,207],[4,51],color=BAT,lw=1,ls=':',zorder=2)
    else:
        ax.plot(front_curve[:,0],-front_curve[:,1],color=REF,lw=2,ls='--',zorder=1)
        for sign in [-1,1]:
            ax.plot([sign*71,sign*71],[-43,-147],color=REF,lw=2,ls='--')
            ax.plot([sign*67.5,sign*67.5],[-44,-147],color=REF,lw=1,ls=':')
            # Side band from the reference leg to the rear chamber.
            band=np.array([[sign*69.25,-147],[sign*68,-164],
                           [sign*64,-181],[sign*58.5,-194]])
            ax.plot(band[:,0],band[:,1],color='#627386',lw=9,alpha=.3)
        dim(ax,[-67.5,-132],[67.5,-132],'参考两腿内距 135',offset=0)

figures=[]
for view,title,filename in [
    ('front','前视｜前框仅相机','01_front.png'),
    ('side','侧视｜前相机＋后脑空腔','02_side.png'),
    ('top','俯视｜镜腿不挂器件','03_top.png')]:
    fig,ax=plt.subplots(figsize=(13.3,8.4),dpi=150)
    fig.patch.set_facecolor('#f8fafc')
    ax.set_facecolor('#f8fafc')
    reference(ax,view)
    shape(ax,battery,view,BAT,.07 if view=='front' else .24,view=='front',zorder=2)
    shape(ax,camera_cavity,view,CAM,.025,True,zorder=8)
    shape(ax,camera,view,CAM,.34,zorder=9)
    shape(ax,usb_reserve,view,RES,.06,True,zorder=8)
    port=projected(usb_mouth[None,:],view)[0]
    ax.scatter(*port,color=RES,s=24,zorder=13)
    if view=='front':
        p=projected(optical_world,view)
        ax.scatter(p[:,0],p[:,1],color='#593b1d',s=[35,22,35],zorder=12)
        note(ax,'相机：89.94 × 30 × 25\n上移 2；前脸整块露出',[-22,48],[-55,104],CAM)
        note(ax,'两侧均无器件舱\n布局参照 WOAD',[71,34],[101,49])
        note(ax,'后脑占位的投影\n117 宽 × 47 高',[-58.5,7],[-119,-25],BAT)
        note(ax,'左端 USB 预留不变\n从带壳占位侧边向外 30',[-66,30],[-127,90],RES)
        note(ax,'相机上沿 59.24\n比参考上沿高 4.24',[0,59.24],[24,88],'#b45b45')
        ax.set_xlim(-140,168); ax.set_ylim(-45,119)
    elif view=='side':
        note(ax,'相机下倾 20°；上移 2\n旋转包络 36.74 高 × 33.75 深',[-20,41],[-45,111],CAM)
        note(ax,'前框中央总深度暂定 42.03\n相机腔包络 35.03＋前后壁各 3.5',[-18,12],[25,99],CAM)
        ax.plot([frame_front_y,frame_front_y],[9,64],color=CAM,lw=.9,ls=':')
        ax.plot([frame_rear_y,frame_rear_y],[9,64],color=CAM,lw=.9,ls=':')
        dim(ax,[frame_front_y,12],[frame_rear_y,12],'42.03',offset=0,color=CAM)
        dim(ax,[frame_front_y,82],[wing_end_y,82],'含弧形侧翼至镜腿起点 82.39',offset=0,color=REF)
        note(ax,'15 mm 可调织带连接\n镜腿末端 → 后脑舱',[171,45.5],[118,88])
        note(ax,'后脑空腔 117 × 47 × 15\n盖从后方打开；配重自行放',[200,27],[145,-23],BAT)
        dim(ax,[0,0],[190,0],'前参考面 → 后脑空腔前面 190（暂定）',offset=-13)
        # Optical axis tilted 20 degrees below horizontal.
        front=camera_world([[0,0,0]])[0]
        p=projected(front[None,:],view)[0]
        ax.annotate('',xy=p+np.array([-22*c,-22*s]),xytext=p,
                    arrowprops=dict(arrowstyle='->',color=CAM,lw=1.8))
        ax.plot([p[0]-25,p[0]],[p[1],p[1]],color=CAM,lw=.8,ls=':')
        ax.set_xlim(-58,236); ax.set_ylim(-45,125)
    else:
        note(ax,'相机居中\n前脸整块露出；无透明罩',[0,25],[-117,57],CAM)
        note(ax,'镜腿保持空\n不放主板、不挂器件',[71,-83],[100,-57])
        ax.plot([-47,-47],[-frame_rear_y,-frame_front_y],color=CAM,lw=.9,ls=':')
        dim(ax,[47,-frame_rear_y],[47,-frame_front_y],'前框中央深度 42.03',offset=-10,color=CAM)
        note(ax,'USB-C 侧\n30 mm 插线/弯线预留',[-65,-1],[-126,-54],RES)
        note(ax,'原参考轮廓单独重建\n虚线只是摆放参考',[50,-12],[101,38])
        note(ax,'左右可调带\n长度随佩戴调节',[-67,-172],[-130,-178])
        note(ax,'后脑块横放：117 宽\n47 高 × 15 深；后开盖',[0,-201],[83,-212],BAT)
        dim(ax,[-58.5,-205],[58.5,-205],'117',offset=-15)
        ax.set_xlim(-142,169); ax.set_ylim(-244,78)
    ax.set_aspect('equal',adjustable='box')
    ax.axis('off')
    fig.suptitle(title,fontsize=23,fontweight='bold',color='#203447',y=.96)
    fig.text(.04,.88,'第一步修订 · 仅相机＋电池空腔 · mm · 灰虚线为参考轮廓；尚未生成打印外壳',
             fontsize=12,color='#5a6a78')
    fig.text(.04,.025,'橙：相机与腔体预留   紫：后脑电池空腔   蓝虚线：USB 插线预留\n'
             '42.03 为中央前框深度预算；前后壁各 3.5 是暂定值。实际佩戴、鼻托接触及打印装配：没查。',
             fontsize=11,color='#5a6a78')
    fig.subplots_adjust(left=.035,right=.975,bottom=.11,top=.83)
    fig.savefig(HERE/filename,facecolor=fig.get_facecolor())
    plt.close(fig)
    figures.append(filename)

def bbox(points):
    lo,hi=points.min(0),points.max(0)
    return {'min_xyz_mm':lo.tolist(),'max_xyz_mm':hi.tolist(),
            'size_xyz_mm':(hi-lo).tolist()}

report={
 'stage':'1 revised: camera-only WOAD layout; no printable enclosure',
 'scope':{'front_contents':['camera'],'rear_contents':['battery_cavity'],
          'leg_contents':[],'mainboard_reserved':False},
 'reference':{'source':'BTTF Glasses Normal; independent reconstruction',
              'width_mm':142,'depth_mm':147,'height_mm':55,
              'nose_notch_width_height_mm':[18,20],
              'leg_inner_width_mm':135,'wall_mm':3.5,
              'curve_measured_anchors_x_rearward_mm':[[0,0],[50,12],[60,19]],
              'curve_transition_anchors_design_choice_mm':[[65,25],[68.5,33],[71,43]],
              'leg_height_mm':19,'leg_taper_end_y_mm':80},
 'camera':{'nominal_complete_case_mm':camera_size.tolist(),'tilt_down_deg':20,
           'rotated_height_depth_calculated_mm':[camera_rotated_height,camera_rotated_depth],
           'raised_from_previous_pose_mm':camera_raise_mm,
           'center_xyz_mm':camera_center.tolist(),'placed_bounds':bbox(camera),
           'proposed_future_cavity_local_width_height_depth_mm':[90.94,31,26],
           'cavity_clearance_per_face_mm':.5,
           'placed_cavity_bounds':bbox(camera_cavity),
           'projected_gap_above_nose_notch_mm':2.5,
           'case_backmost_to_reference_front_plane_mm':1.5,
           'above_reference_top_mm':float(camera[:,2].max()-55),
           'optical_centers_step_source_xyz_mm':optical_sources,
           'optical_markers':'schematic dots, not measured window openings',
           'usb_mouth_step_source_xyz_mm':usb_mouth_source.tolist(),
           'usb_direction_step':[-1,0,0],
           'usb_bend_reserve_beyond_nominal_envelope_mm':30,
           'usb_reserve_bounds':bbox(usb_reserve),
           'usb_reserve_pose_note':'moves up 2 with camera; X/Y and 30 mm span unchanged',
           'usb_reserve_beyond_reference_halfwidth_mm':3.97,
           'finished_case_to_internal_step_registration':'没查',
           'finished_window_aperture_sizes':'没查',
           'complete_camera_mount_holes':'没查; prefer slot and M2 cover after approval'},
 'front_frame_depth':{'definition':'world-Y distance between proposed central front/rear outer envelope planes; excludes curved wings and USB cable reservation',
                      'camera_case_rotated_depth_mm':camera_rotated_depth,
                      'cavity_rotated_depth_mm':float(cavity_rear_y-cavity_front_y),
                      'tentative_world_y_front_wall_mm':front_wall_mm,
                      'tentative_world_y_rear_wall_mm':rear_wall_mm,
                      'front_plane_y_mm':float(frame_front_y),
                      'rear_plane_y_mm':float(frame_rear_y),
                      'total_depth_mm':float(frame_depth),
                      'whole_front_outline_depth_to_leg_start_mm':float(whole_front_depth),
                      'whole_front_outline_rear_y_mm':wing_end_y,
                      'whole_front_outline_status':'计算；包含参考弧形侧翼至当前设定的直镜腿起点 Y=43，未建外壳',
                      'status':'设定＋计算；仅深度预算，非已建外壳；前脸光学开口待建'},
 'battery':{'cavity_width_height_depth_mm':[117,47,15],
            'bounds':bbox(battery),'front_y_mm':190,
            'position_status':'proposal, adjustable band; wearer head measurements 没查',
            'lid_direction':'rearward; only indicated, not designed'},
 'connection':{'type':'reference hard legs + left/right adjustable webbing to rear chamber',
               'proposed_band_width_mm':15,'leg_end_y_mm':147,
               'attachment_height_z_mm':45.5,'exact_strap_length_and_fit':'没查'},
 'deferred_shell_details':{'vents':'没查; camera rear only after approval; no board chamber',
                          'rear_type_c_opening':'没查; appearance opening after approval',
                          'microphone_hole':'planned diameter 1.5, downward near one front edge; location 没查',
                          'M2_cover_and_print_orientation':'没查; no printable parts at this stage'},
 'images':figures}
(HERE/'placement_values.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
record = f'''第一步修订：前相机＋后脑电池空腔（WOAD 布局）
主板及所有主板预留取消；镜腿不挂器件。尚未建打印外壳。
单位 mm；“设定”“计算”不是实物或最终外壳实测。

相机带壳占位：89.94 宽 × 30 高 × 25 深，采用用户给定尺寸。
下倾角：20°（设定）；相对上一版向上移动 2，X/Y 不变。
下倾后包络：36.741 高 × 33.753 深（计算）。
中心：X=0、Y={camera_center[1]:.3f}、Z={camera_center[2]:.3f}（设定）。
相机 Z 范围：22.500～59.241；比 55 参考上沿高 4.241（计算）。
鼻缺口参考：18 宽 × 20 高；相机在缺口上方投影间隙 2.500（计算）。

拟相机腔：90.94 宽 × 31 高 × 26 深；各局部表面间隙 0.5（设定）。
相机腔旋转后包络：38.023 高 × 35.035 深（计算）。
前框中央总深度预算：{frame_depth:.3f}。
构成：相机腔前后包络 35.035＋前壁 3.5＋后壁 3.5。
前后壁暂沿全局 Y 方向预留；Y 边界 {frame_front_y:.3f}～{frame_rear_y:.3f}。
此深度不含弧形侧翼、镜腿和横向 USB 线；是预算，不是已建外壳测量。
若把弧形两翼也计入，到当前直镜腿起点 Y=43 的前框前后包络为 {whole_front_depth:.3f}。
参考件 147 深包含镜腿；不要把它与相机处的框体厚度混用。
前脸整块露出，无透明罩；圆点只标光学中心，不代表开孔大小。

左端 USB：从带壳占位左边界 X=-44.97 向外预留 30 至 X=-74.97。
预留随相机上移 2，横向位置和 30 长度不变。
线缆预留比 142 参考轮廓左侧多出 3.97；不代表最终外壳宽度。
成品接口口沿与最终外壳的准确对应尺寸：没查。

后脑电池空腔：117 宽 × 47 高 × 15 深（用户给定，本版不变）。
位置：X=-58.5～58.5、Y=190～205、Z=4～51（布局设定）。
后脑不留其他器件。盖从后方打开；盖与锁扣/螺孔几何没查、尚未设计。
连接方案：硬镜腿＋左右 15 宽可调织带；实际带长与佩戴贴合没查。
参考轮廓：Normal 142 宽 × 147 深 × 55 高，两腿内侧间距 135。
轮廓按用户提供锚点独立重建；原 3MF 网格未修改。

没查：相机成品带壳与内部 STP 的定位关系、光学开孔大小、成品安装孔、
实际鼻托接触、打印装配、卡槽与 M2 盖板装拆路径、各打印件朝向。
后续外观孔：相机后方散热缝、后脑 Type-C、前框下沿朝下的 1.5 麦克风孔。
开孔最终位置/尺寸没查；麦克风 1.5 仅为用户给定设定。
主板舱散热缝随主板舱取消。确认第一步后才建外壳。

完整坐标与来源状态见 placement_values.json。
'''
(HERE/'values_camera_only.txt').write_text(record,encoding='utf-8')
(HERE/'RUN.txt').write_text(
    'Camera-only Stage 1. No printable enclosure.\n'
    'Run build_stage1.py with Python + numpy + matplotlib + scipy.\n'
    'Included camera_step_measurements.json supplies STEP port data.\n'
    'No mainboard mesh or space is used.\n'
    'Runtime: Python 3.11\n'
    'Records: placement_values.json, values_camera_only.txt.\n'
    '42.03 mm is the proposed central frame depth with 3.5 mm\n'
    'world-Y front and rear reservations.\n',encoding='utf-8')
assert np.isclose(camera[:,2].min(),22.5)
assert np.isclose(usb_reserve[:,0].min(),-74.97)
assert np.isclose(usb_reserve[:,0].max(),-44.97)
assert np.allclose(battery_hi-battery_lo,[117,15,47])
assert report['scope']['mainboard_reserved'] is False and 'board' not in report
assert np.isclose(frame_depth,42.034632583529344)
package_files = figures+['build_stage1.py','placement_values.json',
                 'camera_step_measurements.json','values_camera_only.txt','RUN.txt']
with zipfile.ZipFile(HERE/'stage1_camera_only.zip','w',zipfile.ZIP_DEFLATED) as archive:
    for filename in package_files:
        archive.write(HERE/filename,filename)
# Remove only this task's superseded earlier bundle; never source files.
(HERE/'stage1_layout.zip').unlink(missing_ok=True)
print('STAGE1_COMPLETE',json.dumps({'camera_height_depth':[camera_rotated_height,camera_rotated_depth],
      'camera_above_reference_top':report['camera']['above_reference_top_mm'],
      'front_frame_central_depth_mm':float(frame_depth),
      'images':figures},ensure_ascii=False))
