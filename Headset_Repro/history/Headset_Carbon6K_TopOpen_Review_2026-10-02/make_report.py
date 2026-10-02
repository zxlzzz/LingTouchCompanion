from pathlib import Path
import json,hashlib
import numpy as np
P=Path(__file__).resolve().parent;ROOT=P.parent
g=json.loads((P/'geometry/geometry_values.json').read_text());s=json.loads((P/'audit/solid_collision_audit.json').read_text());h=json.loads((P/'audit/surface_clearance_audit.json').read_text());m=json.loads((P/'model_verification.json').read_text());t=json.loads((P/'audit/box_plate_thickness.json').read_text())
sha=hashlib.sha256((P/'geometry/rear_unified_preview.npz').read_bytes()).hexdigest()
assert sha==s['rear_source_sha256']==h['rear_source_sha256']==m['source_mesh_sha256']
assert t['eroded_empty']
# Geometry of the supports and straps is exactly unchanged from the previous
# Carbon6K candidate; verify arrays rather than inferring from construction.
unchanged={}
for name in ['rear_tray','rear_inner_surface','rear_outer_surface','rear_left_rib','rear_right_rib','rear_central_join','strap_left','strap_right','straps_preview']:
 a=np.load(P/'geometry'/(name+'.npz'));b=np.load(ROOT/'Headset_Carbon6K_RearReview_2026-10-02/geometry'/(name+'.npz'))
 unchanged[name]=bool(np.array_equal(a['v'],b['v']) and np.array_equal(a['f'],b['f']));assert unchanged[name],name
unchanged['front_geometry_sha256']=hashlib.sha256(Path(g['sources']['front']).read_bytes()).hexdigest();assert unchanged['front_geometry_sha256']==s['front_source_sha256']=='83af1ea68a0066a13382948085567001e2e447c0619bcc3108df7510d6e9b9da'
(P/'audit/unchanged_inputs.json').write_text(json.dumps(unchanged,indent=2),encoding='utf8')
lo,hi=h['rear_inner_surface']['continuous_surface_distance_bound_mm']
text=f'''# Carbon6K后脑件：上端敞开检查版

电池仍沿X横放，改为从上方放入、向上取出。原侧端装入口取消；两端有挡壁，+X接口端保留接线豁口。弧托、两道竖肋、中间薄连接、穿带位置、带子路径、前件及头模摆位均没有移动。原侧插检查版文件保留，本文件取代它作为当前后脑候选。

## 改了什么

- 去掉整个顶壁，顶口直通，取放方向从X改为Z。
- 内腔沿X仍长91，两端各2厚挡壁，因此盒宽从93变成95；外部前后27.4、高27.4及中心Z=39.2保留。
- 保留外部高度后，去掉原2厚顶壁，内底Z=27.5到口沿Z=52.9，**实际净深25.4**。原91×23.4×23.4容纳包络仍完整保留，但不能把现在的实际净深写成23.4。
- 原底部轴向侧插弹片取消，改为背壁U缝弹片；0.8的钩在圆柱上半侧，阻止向上滑出。
- 接口端豁口宽18、从口沿向下19.7，底Z=33.2。它不是整端敞开，完整Ø22.8圆柱不能从此处沿X装入。实际USB和插头细部没查，豁口是当前名义留口。
- 穿带板根部采用R1.5减料，穿带板及竖缝的坐标不改。盒、弹片及两块穿带板合并后，通过最大内接球厚度≤3的保守几何核查。

## 实际数值

| 项目 | 模型实际值，mm | 已核结果 |
|---|---|---|
| 后脑整体宽×前后×高 | **95×35.4×32**；X=±47.5，Y=195.3～230.7，Z=23.2～55.2 | 已量 |
| 实体体积 | **{s['volume_cm3']:.6f}cm³** | 已量；单个封闭连通打印实体 |
| 盒子外尺寸 | 95×27.4×27.4 | 已量 |
| 内部直通净通过尺寸／底至口沿深度 | 91×23.4／25.4 | 顶板不存在；外上棱圆角处口沿会变薄 |
| 箱底、前后壁、端挡壁 | 常规板面2；外圆角R3、原内底圆角R1 | 薄壁空心，没有填实 |
| 电池占位、中心 | Ø22.8×90.4，轴沿X；中心(0,217,39.2)，端X=±45.2 | 长度方向左右各0.3，前后与底各0.3；电池顶50.6，低于口沿2.3 |
| 顶部取放完整路径 | +Z平移27.401，退出后最低Z=55.201 | 与后件去小钩、当前前件、带子的连续扫掠交叠均0mm³；反向即放入 |
| 弹片位置与尺寸 | 背壁X=27～33.8，宽6.8；根Z=32，自由端44，长12；U缝0.6；钩向内凸0.8，Z=42.8～43.6 | 放稳占位体与钩也不相交；向上约{s['spring']['free_upward_play_before_nominal_circle_hook_contact_mm']:.6f}开始碰钩，需要弹片后让；几何最大后让0.5，实物弹性没查 |
| 接口端豁口 | +X端，Y=208～226，宽18；Z=33.2～52.9，深19.7 | 不挡顶部取放；真实口、按钮与线插头匹配没查 |
| 弧托宽／高／名义厚度 | 40／27.4／2.5 | 原网格逐顶点、逐三角面相同 |
| 弧托整面距头模 | 保守整面界限**{lo:.6f}～{hi:.6f}** | 满足0～2；这是连续面距离的保证范围，不是精确最大／最小值 |
| 后脑实体到头模最近距离 | **{h['rear_head_continuous_minimum']['distance_mm']:.6f}** | 连续三角面无相交；所有后脑顶点在头模后侧。头模颈部开口，不声称头模体积布尔 |
| 后脑与前件／带子 | 重叠均0mm³ | 当前前件只读使用，没有修改 |
| 两侧带子自由长度 | 左**46.303375**，右**46.307978** | 都在40～60；路径与上一版逐网格相同 |
| 两块穿带板／竖缝 | 厚3，高32，Z=23.2～55.2；26×3竖缝，Y=198.3～201.3 | X范围沿用±43.5～46.5，位于盒端±47.5以内 |
| 连接 | 原两道3厚竖肋＋中央2厚薄舌 | 连接件和弧托与上版逐网格相同；大空当未填实 |
| 厚度核查范围 | 盒＋新弹片＋两穿带板用半径1.5的内接球多面体侵蚀，结果为空 | 保守核得这块组合体最大内接球厚度≤3。弧托名义2.5、竖肋3、薄舌2；肋与弹片根部按原例外。全件各融合处最大法向厚度没查，不把内接球指标当所有方向的法向测量 |

圆柱尺寸与USB-C充放电规格参考[NITECORE官方产品页](https://www.nitecore.com/product/carbon_battery_6k)。没有依据照片比例编造USB孔位置、按钮尺寸或插头尺寸。

取放路径采用包住真实圆的384边外切圆柱（半径11.400382）在起止两个位置的凸包，它等于完整连续竖直平移包络；没有只检查离散几个高度。小钩的相交由弹片让位处理，实际拆装、卡紧程度和耐久没查。

## 打印朝向与支撑

**底部朝下、上开口朝上**，即保持佩戴坐标Z向上，再落到平台。最低是两侧穿带板下端Z=23.2；盒底与弧托下沿Z=25.5，比最低面高2.3，因此盒底外侧、弧托底部及薄连接／肋的外部悬伸处需要可拆支撑。相机和电池只是图中的占位体，不随打印件导出。

盒内没有顶棚，不需要内部支撑。U缝与弹片后面不填支撑，避免粘死弹片；0.8小钩悬伸和0.6缝的打印表现没查。真实切片、支撑拆除、弹性及实物佩戴没查。本3MF仍是佩戴朝向检查文件，尚未定版。
'''
(P/'Measurements_and_Printing.md').write_text(text,encoding='utf8');print('Report written; unchanged inputs and export verified.')
