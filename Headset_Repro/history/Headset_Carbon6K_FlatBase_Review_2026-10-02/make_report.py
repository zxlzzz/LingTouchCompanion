from pathlib import Path
import json,hashlib
import numpy as np
P=Path(__file__).resolve().parent;ROOT=P.parent
g=json.loads((P/'geometry/geometry_values.json').read_text())
s=json.loads((P/'audit/solid_collision_audit.json').read_text())
h=json.loads((P/'audit/surface_clearance_audit.json').read_text())
m=json.loads((P/'model_verification.json').read_text())
t=json.loads((P/'audit/box_plate_thickness.json').read_text())
sha=hashlib.sha256((P/'geometry/rear_unified_preview.npz').read_bytes()).hexdigest()
assert sha==s['rear_source_sha256']==h['rear_source_sha256']==m['source_mesh_sha256']==t['rear_source_sha256']
assert t['eroded_empty']
unchanged={}
for name in ['rear_tray','rear_inner_surface','rear_outer_surface','rear_left_rib','rear_right_rib','strap_left','strap_right','straps_preview']:
 a=np.load(P/'geometry'/(name+'.npz'))
 expected=json.loads((P/'inputs/reference_fingerprints.json').read_text(encoding='utf8'))[name]
 unchanged[name]=hashlib.sha256(a['v'].tobytes()+a['f'].tobytes()).hexdigest()==expected;assert unchanged[name],name
unchanged['front_geometry_sha256']=hashlib.sha256(Path(g['sources']['front']).read_bytes()).hexdigest()
assert unchanged['front_geometry_sha256']==s['front_source_sha256']=='83af1ea68a0066a13382948085567001e2e447c0619bcc3108df7510d6e9b9da'
# Verify each actual base plane from mesh vertices rather than nominal inputs.
base={}
for name in ['rear_box','rear_tray','rear_left_rib','rear_right_rib','rear_central_join','rear_left_strap_plate','rear_right_strap_plate']:
 v=np.load(P/'geometry'/(name+'.npz'))['v'];base[name]=float(v[:,2].min());assert abs(base[name]-25.5)<1e-6
unchanged['verified_base_min_z_mm']=base
(P/'audit/unchanged_inputs_and_base.json').write_text(json.dumps(unchanged,indent=2),encoding='utf8')
lo,hi=h['rear_inner_surface']['continuous_surface_distance_bound_mm']
text=f'''# Carbon6K后脑件：补侧壁、底部齐平检查版

上端敞开，电池仍沿X横放，从上方放入、向上取出。两个端面都补成2mm侧壁，接口端仅留12×6mm的小通孔。弧托贴头形状、两道竖肋、穿带孔和带子走向不移动，当前前件没有修改。

中间2mm连接薄舌由顶部移到底部。盒底、弧托下沿、竖肋、薄舌和穿带板的最低面统一到Z=25.5。没有把托与盒之间的空当填实。

为使穿带板也落在同一底面，板的底边从23.2升到25.5，上沿仍55.2，实际高度由32改为29.7；26×3竖缝的坐标不变，因此**竖缝下边料仅0.7mm**。这项未满足原先32mm板高，属于本次齐底处理的明确变化；边料强度和实物打印没查。

## 实际数值

| 项目 | 模型实际值，mm | 核查结果 |
|---|---|---|
| 整体宽×前后×高 | **95×35.4×29.7**；X=±47.5，Y=195.3～230.7，Z=25.5～55.2 | 已量 |
| 实体体积 | **{s['volume_cm3']:.6f}cm³** | 单个封闭连通实体；导出的3MF顶点、三角面与核查网格一致 |
| 盒子外尺寸 | 95×27.4×27.4 | 盒中心Z=39.2保留 |
| 内腔直通尺寸／内底至口沿净深 | 长91、前后23.4／深25.4；内底27.5，口沿52.9 | 顶壁去掉后实际深度为25.4；原23.4高容纳包络仍在，不将实际深度写成23.4 |
| 常规盒壁 | 前后、底部和两端均2；外纵向圆角R3、内底R1 | 内部空；上口圆角处壁缘会变薄；接口通孔和U缝处除外 |
| 补上的端侧壁 | X=-47.5～-45.5和45.5～47.5 | 两端不作为电池装入口 |
| 接口小孔 | +X端；12宽(Y)×6高(Z)，Y=211～223，Z=36.2～42.2 | 当前名义孔；实际USB中心、插头和线缆匹配**没查**，不能声称接口已经对齐 |
| 电池占位及中心 | Ø22.8×90.4；中心(0,217,39.2)，轴向X | 左右、前后与底部各0.3净隙；电池顶50.6，比口沿低2.3 |
| 统一底部 | 盒底、弧托、两竖肋、中央薄舌、两穿带板最低Z均25.5 | 实际网格核查误差小于0.000001；盒底外圆角本身保留，不声称整个弯曲面均共面 |
| 中央薄连接 | X=±4，Z=25.5～27.5，厚2；实际Y约199.751～204.8 | 改在下部，和盒底相接，顶部原薄舌取消 |
| 两竖肋 | 每道3厚，Z=25.5～52.9 | 与上一候选网格相同，没有填实两肋间的空当 |
| 弧托 | 宽40、高27.4、名义厚2.5 | 贴头形状逐顶点、逐面未变 |
| 弧托整面到头模 | 连续面保守保证范围**{lo:.6f}～{hi:.6f}** | 满足0～2；不是精确最小／最大距离 |
| 后脑实体到头模最近距离 | **{h['rear_head_continuous_minimum']['distance_mm']:.6f}** | 连续面不相交，后脑实体在头模后侧；头模颈部不是封闭实体，不声称头模体积布尔 |
| 后脑与当前前件／带子重叠 | 均0mm³ | 已核 |
| 带子悬空段 | 左**46.303375**，右**46.307978** | 满足40～60；镜腿截短0；这是几何悬空长度，不是含折返的裁剪长度 |
| 穿带板与孔 | 厚3、高29.7，Z=25.5～55.2；孔26×3，Z=26.2～52.2，Y=198.3～201.3 | 孔和带子中心Z=39.2未动；孔下边料**0.7**，孔上边料3；强度没查 |
| 顶部放入／取出路径 | 电池沿+Z平移27.401后完全退出，最低Z=55.201 | 连续扫掠与除小钩外的后件、带子、前件交叠均0mm³；反向即放入 |
| 弹片与小钩 | 背壁弹片宽6.8、自由长12、U缝0.6；钩内凸0.8 | 到位电池与钩也不相交；向上约{s['spring']['free_upward_play_before_nominal_circle_hook_contact_mm']:.6f}开始碰钩，名义最大后让0.5；实物弹性、夹持力及耐久没查 |
| 厚度检查 | 常规盒壁2、托2.5、穿带板3、肋3、薄舌2 | 盒+弹片+穿带板最大内接球直径保守界限≤3；肋/弹片根部按原例外；全件融合处最大法向厚度没查，未将内接球指标当作所有方向的厚度 |

电池的尺寸及USB-C规格参考[NITECORE官方产品页](https://www.nitecore.com/product/carbon_battery_6k)。本件接口孔没有根据照片比例猜测真实接口位置。

取放核查用包住真实圆柱的384边外切柱体，在起止位置的凸包覆盖完整连续竖直平移路径；没有只检查几个离散高度。小钩需要弹片后让，几何让位要求不等于已经验证实物能弹开。

## 打印朝向与支撑

底部朝下，上开口朝上。切片时把Z=25.5底面落到平台：盒底平面区、弧托下沿、竖肋、中央薄连接和穿带板同时接触平台，消除此前盒底比穿带板底高2.3mm的悬空。

盒内没有顶棚，不需要封闭腔内支撑。穿带竖缝上端有3mm短桥，接口孔上端有12mm桥，需要按切片桥接能力判断是否加可拆支撑；这些开口处支撑可拆。盒底外圆角及0.8mm小钩处需检查首层和悬伸效果。弹片U缝和弹片背后避免支撑粘死。真实切片、0.7mm下边料强度及材料弹性没查。

3MF保持佩戴坐标，只含后脑件；头模、前件、带子和电池只出现在图中，不随打印实体导出。这是检查版，待确认后才出定版。
'''
(P/'Measurements_and_Printing.md').write_text(text,encoding='utf8')
print('Report written; actual base planes and source-matched checks verified.')
