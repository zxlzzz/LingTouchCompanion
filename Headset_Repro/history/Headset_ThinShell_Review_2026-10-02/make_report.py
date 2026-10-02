"""Write the readable measurement table from the current audited candidate."""
from pathlib import Path
import hashlib,json

P=Path(__file__).resolve().parent
def read(path):return json.loads((P/path).read_text(encoding='utf8'))
g=read('geometry/geometry_values.json')
c=read('geometry/readonly_geometry_checks.json')
s=read('geometry/surface_visibility_thickness_checks.json')
n=read('audit/nose_clearance_actual.json')
p=read('audit/print_orientation_actual.json')
o=read('optics/optics_audit.json')
files=read('review_model_files.json')
assert not str(n.get('revision_status','')).startswith('Pre-repair')
assert not str(p.get('revision_status','')).startswith('Pre-repair')
for record in [n,p]:
    for name,digest in record['input_sha256'].items():
        assert hashlib.sha256((P/'geometry'/(name+'.npz')).read_bytes()).hexdigest()==digest
assert files['front']['source_mesh_sha256']==n['input_sha256']['front_unified_preview']
assert s['front_mesh_sha256']==n['input_sha256']['front_unified_preview']
v=g['volume_cm3'];h=g['maximum_roof_z_mm'];front=-g['frontmost_y_mm']
b=files['front']['bounds_xyz_mm'];dims=[b[1][i]-b[0][i] for i in range(3)]
def link(name,label=None):return '['+(label or name)+']('+str(P/name).replace('\\','/')+')'
visibility=s['sampled_external_visibility']
face=s['original_face_side_material_samples']

text=f'''# 薄壁前件检查版：数值与打印说明

这是佩戴坐标的检查模型，不是打印定版。前件重新从 BTTF Normal 原网格构建；后脑件与已通过的预览网格一致。相机、镜腿耳片、头模摆位和后脑位置均保留。

模型：{link('Front_ThinShell_Review_Wearing.3mf','前件 3MF')}；{link('Rear_Review_Wearing.3mf','后脑件 3MF')}。两个文件都没有打印旋转和平台平移；文件回读后顶点及三角面与佩戴坐标源数据逐项相同。

## 必须满足的条件

| 条件 | 这一版实际值／已查范围 | 结果 |
|---|---|---|
| 最前点距 BTTF 正中前表面 ≤37.5 | 最前 Y=−{front:.6f}，距离 {front:.6f} | 满足 |
| 相机区最高 Z≤60 | Z={h:.6f}，高出 {h-60:.6f}；固定相机、2mm 平行顶壁、后端到原上沿贴脸位置的投影不变时，此候选做到的最高点就是 {h:.6f} | **不满足** |
| 两翼与镜腿 Z≤55.2 | 两翼上限 55.2；旧件上沿 55.175675；耳片上沿 55.2 | 满足高度；翼顶与高筒顶之间有台阶，未做到连续顺降 |
| 宽度不超过 BTTF；下方不低于 Z=0 | X=±71.156651，总宽 {dims[0]:.6f}，与原件相同；最低 Z=0 | 满足 |
| 除入口切除外，原贴脸面不改 | 原件只减去规定入口／轴向退出包络；与此目标的实体对称差 {c['original_modification_vs_only_entry_cut_symmetric_difference_mm3']:.6f} mm³ | 满足原面保护 |
| 新材料不越原贴脸边界 | 原曲面包络裁切后，有限表面核查最大后伸 {face['maximum_rear_y_overrun_mm']:.6f}；核查 {face['samples']} 个点。原件上沿以上没有实际贴脸面，顶壁后界采用上沿后表面的竖直投影 | 实际旧面范围已核；上方接合位置仍有规格冲突 |
| 相机整机沿光轴向后退出，除小钩外无碰撞 | 完整轴向扫掠与前件（去小钩）交叠体积 {c['complete_axial_retreat_sweep_intersection_excluding_hooks_mm3']:.6f} mm³；在规定安放位置，相机与前件交叠 {c['camera_actual_pose_intersection_mm3']:.6f} mm³ | 占位体路径满足；实际弹片释放／实装没查 |
| 外面只从正面镜头窗看见相机，贴脸面除外 | 已核 {visibility['tested']} 条外向射线；意外无遮挡 {visibility['clear_unexpected']}；透过指定窗口 {visibility['clear_through_specified_window']}。任意连续方向的完整可见性证明：没查 | 有限方向核对未发现其它露出 |
| 官方 STP 三光学中心距窗边 ≥8 | STP 原生前视中心 RGB(−22,0)、发射(7,0.005)、ToF(22,0)。**假设** STP 光学基线对齐整机前脸中心时，内窗余量分别 10、9.995、10。STP 与带壳整机的真实配准及实装余量：**没查** | 尚不能据此认定实装通过 |
| 新增 Y<0 实体到头模鼻子 ≥2 | 连续三角面最小距离 {n['minimum_distance_mm']:.6f}；沿用原头模与原试摆，无相机／头模移位 | 满足 |
| 新壳壁 2；除钩根外任何处 ≤3 | 中部平面板法向厚 2；翼面对应内外面的法向偏移 2。全部融合接头的全局最大局部厚度：**没查**。保留旧耳片厚左 3.259046／右 3.415623 | 板面尺寸已核；全局≤3尚未建立；旧耳片按“沿用”保留 |
| 封闭／不可拆空腔不需要内部支撑 | 佩戴模型绕 X 轴 −65° 时，全部真实封腔面和筒下主腔面按常用 45° 判据核查，低于 45° 的面为 0；最小约 45°，没有角度余量 | 几何判据通过；切片／实物没查 |
| 前件总体积，不超过100cm³ | **{v:.6f} cm³**；原件 44.288789cm³，入口切除 9.160959cm³；净体积保留内部空气，不把外包络算成实心 | 小于100；这一版没有大片填实 |

## 模型里的尺寸

| 项目 | 实际数值，mm |
|---|---|
| 前件总体包络，宽×前后×高（包括镜腿耳片） | {dims[0]:.6f}×{dims[1]:.6f}×{dims[2]:.6f} |
| 相机占位，宽×本体高×光轴深 | 89.94×30×25；下倾20°；X=±44.97 |
| 相机后下棱（Y,Z） | (−0.800000,23.600000) |
| 相机前下棱（Y,Z） | (−24.292316,15.049496)；由30×25截面与20°变换计算 |
| 相机前上棱（Y,Z） | (−34.552920,43.240275) |
| 相机后上棱（Y,Z） | (−11.060604,51.790779) |
| 筒内腔截面，宽×本体高 | 90.54×30.8；X=±45.27，局部高度 h=−0.5～30.3 |
| 相机间隙 | 左右各0.3，顶0.3，底0.5；前脸顶住前壁内面 |
| 筒外截面 | 94.54×34.8；X=±47.27，h=−2.5～32.3 |
| 前壁光轴坐标 | 内面 t=25，外面 t=27，法向厚2 |
| 筒顶及筒底 | 与相机顶底平行，法向厚2；筒顶外面 h=32.3 |
| Z=0 底面 | Z=0～2；鼻道正中段不做底面 |
| 鼻道 | 总宽30，X=−15～15；下方前壁与底板挖通，保留筒底壁和旧鼻缺口顶边 |
| 镜头窗 | 内口68×20，内圆角半径10；外口72×24，外圆角半径12；中心(x,h)=(0,15)，45°倒角 |
| 双弹片 | 中心X=±30；长8、宽6，U缝0.6；小钩从内底面凸起0.8；钩根埋入底壁0.02 |
| 镜腿耳片 | 镜腿截短0；耳片高32，竖缝26×3；上沿Z=55.2；原末端后延12 |
| 两侧松紧带悬空段（保留上版） | 左44.318050，右44.318598；带宽25 |
| 后脑件总体尺寸／实体体积 | 136.6×43.558396×47；45.637094cm³ |
| 后脑弧托 | 中段宽80，壁名义2.5；上一版整面离头模保守界限0.429～1.569；本次未改 |
| 后脑盒内腔 | 117.6×15.6×45；壁与底2；装117×47×15时上露2 |
| 后脑凸点与接口豁口 | 口沿凸点侵入0.8；豁口11×35；竖缝26×3 |
| 后脑连接 | 两道竖肋厚3＋中央小连接；盒与托的大空当保持空气；前后件重叠0（沿用上一版核查） |

前述相机采用给定的带壳尺寸占位，四棱坐标按20°精确变换，未把显示为两位小数的坐标当成另一个畸变截面。官方 STP 的内部光学器件已读，但其完整带壳坐标对应没有查明。

## 打印方向与支撑

**前件建议朝向：**从本次佩戴坐标绕左右轴 X 转 **−65°**，使正面大致朝上、两条镜腿末端靠近平台，再平移落到平台。弧面件没有一整块平面朝下。该旋转后的包络为 {p['printing_envelope_xyz_mm'][0]:.3f}×{p['printing_envelope_xyz_mm'][1]:.3f}×{p['printing_envelope_xyz_mm'][2]:.3f}。交付的检查3MF没有做这些打印旋转。

相机下方两主腔的关键顶棚与前壁均约45°，两翼真实封腔的最差面也约45°。这是逐三角面的几何核查，角度没有余量；没有运行切片验证，也没有实际打印。两翼封腔和筒下不可拆窄腔禁止生成内部支撑。贴脸侧可接近的旧件悬伸面、镜腿／耳片后端需要外部支撑，具体支撑接点、支撑拆除和小钩弹性：没查。不再使用旧版“顶面朝下”的实心前件方案。

**后脑件方向：**盒底朝下、开口朝上。盒侧耳片与根部底面、弧托内侧局部悬伸需要从外部可拆的支撑。内腔保持敞口，不做盖。后脑件直接沿用已通过版。

## 当前没达到的地方

1. 固定相机、2mm平行斜筒顶、后端延伸到原贴脸位置同时保留，最高为Z={h:.6f}，超过60。原BTTF上方没有实际贴脸面，本检查模型将旧上沿后表面竖直投影作为筒顶后界；这不是已经满足了“落在实际贴脸面上”。未移动相机、未截掉顶壁、未放宽上限。
2. 两翼上限55.2与中部屋顶超过60不能在边界处连续顺降；检查版两翼保持55.2，通过侧壁接上，图中保留台阶。
3. U缝贯穿筒底，把筒下两腔与相机腔窄连通。它们仍按不可拆内部支撑区域检查，未借此把内部支撑算成可拆。
4. STP到完整机壳的配准、实装光学窗余量、融合接头全局最大厚度、切片和实际装卸都没有查完，不能据此宣布打印定版通过。

图：{link('01_front.png','前视')}｜{link('02_side.png','侧视')}｜{link('03_top.png','俯视')}｜{link('04_section0.png','正中剖面')}｜{link('05_section30.png','X=30剖面')}。
'''
(P/'Measurements_and_Printing.md').write_text(text,encoding='utf8')
print('Readable measurement table saved.')
