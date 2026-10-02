"""Combine current CAD measurements and independent collision certificates."""
from pathlib import Path
import hashlib,json

P=Path(__file__).resolve().parent
def read(name):return json.loads((P/name).read_text(encoding='utf8'))
g=read('geometry/geometry_values.json');s=read('audit/surface_clearance_audit.json')
c=read('audit/solid_collision_audit.json');band=read('audit/strap_head_clearance.json')
export=read('model_verification.json');baseline=read('baseline_inputs.json')
for name,digest in baseline.items():
    assert hashlib.sha256(Path(name).read_bytes()).hexdigest()==digest,('Changed protected input',name)
sha=hashlib.sha256((P/'geometry/rear_unified_preview.npz').read_bytes()).hexdigest()
assert export['source_mesh_sha256']==sha==s['rear_source_sha256']==c['rear_source_sha256']
assert c['front_source_sha256']==baseline[str(Path(g['sources']['front']).resolve())]
assert abs(export['volume_mm3']-g['rear']['volume_mm3'])<.001
L=g['strap_paths']['left']['free_length_mm'];R=g['strap_paths']['right']['free_length_mm']
lo,hi=s['rear_inner_surface']['continuous_surface_distance_bound_mm']
v=g['rear']['volume_mm3']/1000
def link(name,label):return f'[{label}]({str(P/name).replace(chr(92),"/")})'

text=f'''# Carbon Battery 6K 后脑件检查版

本版取代旧 Rear_Final 的后脑方案，仅交检查模型。前件、镜腿、耳片、头模坐标及摆位保持不动；已核这些源文件的前后指纹相同。模型保持佩戴坐标，没有摆成打印方向。

{link('Rear_Carbon6K_Review_Wearing.3mf','后脑件 3MF')}｜{link('01_front.png','前视')}｜{link('02_side.png','侧视')}｜{link('03_top.png','俯视')}。

## 逐条结果

| 要求 | 当前实际数值／核查范围 | 结果 |
|---|---|---|
| 弧托内面离头模0～2 | **整个三角面的距离保证在{lo:.6f}～{hi:.6f}内**；这是连续表面的保守界，不是精确最小/最大。顶点实测0.997224～1.001083 | 满足 |
| 每侧带子悬空40～60；不改前件 | 左 **{L:.6f}**，右 **{R:.6f}**；带宽25；镜腿截短0，前件未改 | 满足 |
| 后脑件不碰前件 | 交叠体积 **{c['rear_front_intersection']['volume_mm3']:.6f}mm³**；前后Y包络间隔36.229670 | 满足；包络间隔不是求得的欧氏最近距离 |
| 后脑件不碰头模 | 连续三角面最近 **{s['rear_head_continuous_minimum']['distance_mm']:.6f}**，全部后件顶点位于后脑外侧，三角面穿插核无交叉 | 满足；头模颈口非闭合，不冒充头体积布尔结果 |
| 带子不碰头或后脑实体 | 完整25宽示意带面距头最近 **{band['straps_preview']['distance_mm']:.6f}**；自由段 **{band['free_straps']['distance_mm']:.6f}**；与后脑实体交叠0 | 满足；真实布料厚度和贴合弯折没查 |
| 电池沿X完整退出，除小钩外不碰任何实体 | 沿+X连续退出91.001；覆盖真圆柱的连续扫掠与后件（去钩）、带子、前件交叠均 **0mm³**，不是几步离散摆放 | 满足占位体退出路径 |
| 开口不被穿带板或带子遮挡，接口朝开口 | +X敞开；电池接口端面X=45.9，口沿X=46.5，缩进 **0.6**；板与带子不侵入真圆柱退出包络 | 占位体开口核通过；真实USB端细部位置没查 |
| 后件总宽等于盒长，板不超盒两端 | 两者X均为 **−46.5～46.5**，总宽 **93** | 满足 |
| 全部薄壁空心，不填实；除肋/钩根外厚≤3 | 盒普通壁2、弧托名义2.5、穿带板3；肋3、中央薄舌2。板根R2仅减料，实际中高截面局部超3厚区已消除。完整3D融合处最大厚度逐点证书：**没查** | 构造尺寸与主要接头已核；全局最大未穷举 |
| 整体宽×前后×高 | **93×35.4×32**，X±46.5，Y195.3～230.7，Z23.2～55.2 | 已量 |
| 实体体积 | **{v:.6f}cm³**；单个闭合连通实体，3MF回读坐标及三角面与源网格一致 | 已量 |

## 实际结构尺寸

| 项目 | 模型中的数值，mm |
|---|---|
| 电池占位 | Ø22.8×90.4圆柱，轴线沿X；88g由用户提供，未称重 |
| 电池轴端点 | (−44.5,217,39.2)～(45.9,217,39.2) |
| 盒内腔 | 91×23.4×23.4；X=−44.5～46.5，Y205.3～228.7，Z27.5～50.9 |
| 盒外尺寸 | 93×27.4×27.4；X±46.5，Y203.3～230.7，Z25.5～52.9 |
| 盒长为什么是93 | 内腔91＋仅封闭端的一层2mm壁；开口端没有端板 |
| 盒壁／长棱圆角 | 壁2；外圆角R3，内圆角R1，同心相差2 |
| 电池横截面间隙 | 居中时上下、前后各0.3；轴向开端剩0.6，闭端端面贴内壁 |
| 盒子中心 | (0,217,39.2)；内腔因一侧端板，X中心=1，圆柱贴闭端后X中心=0.7 |
| 弧托 | 宽40，X±20；高27.4，Z25.5～52.9；名义厚2.5，内外三角面真实连续最短间距 **{s['tray_inner_outer_minimum']['distance_mm']:.6f}** |
| 两端竖肋 | X−20～−17及17～20，各厚3；高27.4；从弧托实际曲面接到盒前壁，空当不填 |
| 正中薄连接舌 | X±4，Z49.9～51.9，厚2；实际Y202.532142～204.8；只接合中央上方小区域 |
| 穿带板 | 左X−46.5～−43.5，右43.5～46.5；厚3、高32，Z23.2～55.2，Y195.3～203.5 |
| 穿带板前伸 | 相对盒前面Y203.3，向前8；与盒壁连接有0.2重叠；板根R2外圆角减料 |
| 竖缝 | 26×3，Z26.2～52.2，Y198.3～201.3，穿透板厚方向X |
| 弹片 | 底壁U缝0.6；净宽6.8；从X37.1根部到X45.8末端，净长8.7 |
| 小钩 | 从内底面Z27.5凸起0.8，顶Z28.3；底部有根部嵌合；跨末端缝悬伸0.4，未接上另一侧余边 |
| 钩与就位电池 | 未压弹片时，钩与圆柱占位交叠 **{c['battery_rear_with_hook_intersection']['volume_mm3']:.6f}mm³**；盒其余部分交叠0。需要弹片让位，实际弹性／压下量没查 |
| 左带悬空起终点 | (−71.097471,159.070330,39.2)～(−46.5,198.3,39.2) |
| 右带悬空起终点 | (71.106134,159.070330,39.2)～(46.5,198.3,39.2) |
| 槽到槽路径与悬空段 | 左50.803375、右50.807978；各包含贴前耳片外侧的4.5，悬空段不计该4.5 |
| 图中带子 | 宽25，示意厚0.8；真实厚度、未拉伸裁带长度：没查 |

接口端只用圆柱端面占位，没有伪造实际Type-C口、按键或端帽细部。退出核使用384边外包圆柱，半径11.400382，包含半径11.4的真圆，因此“交叠0”覆盖完整圆柱，不只是内接多边形。

## 打印方向与支撑

**−X封闭端朝下，+X敞口朝上。** 从佩戴坐标绕Y轴−90°后落到平台，打印包络32×35.4×93。交付3MF仍是佩戴朝向。

盒子内腔沿打印Z竖直敞开，没有封闭的内顶棚，所以电池腔不需要支撑。弧托、两侧连接肋、正中薄舌以及+X端穿带板的前伸底面，需要从外部可拆的支撑。−X端穿带板随封闭端从平台起印。

弹片末端有0.6宽缝，小钩跨缝悬伸0.4；这是短桥候选，不在缝里放支撑，以免把弹片粘死。具体切片、短桥质量、支撑拆除及实物弹片耐用性：**没查**。

## 本轮边界

五项要求中的贴头距离、带长、不相交、完整退出路径、整体尺寸和体积均已数字核对。没有移动前件、没有扩大限定尺寸，也没有把托与盒间空当填实。

全局融合最大厚度、真实电池端部细节和弹片装卸还未实测，不能把当前检查模型称为全部通过的打印定版。原前件此前的屋顶高度等未通过事项仍保留，本轮没有更改或重新确认它们。
'''
(P/'Measurements_and_Printing.md').write_text(text,encoding='utf8')
(P/'protected_inputs_verification.json').write_text(json.dumps({'unchanged':True,'fingerprints':baseline},indent=2),encoding='utf8')
print('Measurement table saved; protected front/head inputs unchanged.')
