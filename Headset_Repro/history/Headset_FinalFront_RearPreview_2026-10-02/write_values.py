"""Create the review's readable numeric record from the measured final geometry."""
from pathlib import Path
import json
import numpy as np

ROOT=Path(__file__).resolve().parent
rear=json.loads((ROOT/'rear_work/rear_values.json').read_text())
straps=json.loads((ROOT/'connection/strap_values.json').read_text())
front=json.loads((ROOT/'front/front_geometry_values.json').read_text())
audit=json.loads((ROOT/'audit/rear_and_straps_audit.json').read_text())
bb=np.array(rear['unified']['bounds_xyz_mm']); dims=bb[1]-bb[0]
volume=rear['unified']['solid_volume_mm3']/1000
old_volume=123.81415199217647
rear_verification_path=ROOT/'rear/verification.json'
rear_final=json.loads(rear_verification_path.read_text()) if rear_verification_path.exists() else None
rear_exported=rear_final is not None and (ROOT/'rear/Rear_Final.3mf').is_file()
report = {'front':front,'rear':rear,'straps':straps,'audit':audit,
          'rear_final_export':rear_final,
          'delivery_status':'Both approved final printing parts exported' if rear_exported else 'Front exported; rear preview awaiting final export',
          'preview_reports_retained_as_geometric_evidence':True,
          'rear_overall_width_depth_height_mm':dims.tolist(),
          'rear_solid_volume_cm3':volume,
          'rear_solid_volume_reduction_vs_old_percent':100*(1-volume/old_volume)}
(ROOT/'measured_values.json').write_text(json.dumps(report,indent=2),encoding='utf8')

head=audit['head_inner_contact']
bound=head['independent_continuous_entire_surface_conservative_bound_mm']
ls=straps['sides']['left'];rs=straps['sides']['right']
overlap=audit['solid_intersections']['front__rear_unified']['intersection_volume_mm3']
min_gap=min(audit['band_to_middle_support_actual_global_minima'][k]['exact_global_minimum_mm']
            for k in ['left_all_route','right_all_route'])
fb=np.array(front['front_bounds']).reshape(2,3);fd=fb[1]-fb[0]
rear_delivery='后件已确认并输出 rear/Rear_Final.3mf 和独立生成包；几何与批准预览保持一致。' if rear_exported else '后件已确认；后件打印文件正在输出，几何保持批准预览。'
text=f'''两个打印件定版：实际数值记录（2026-10-02）

交付状态
前件已输出 front/Front_Final.3mf 和独立生成脚本。镜腿不截，32高耳片/26×3槽保留当前形状。
{rear_delivery}
头模、摆位、比例不变。后脑接触面是原真实头模衍生网格的中间80mm子集，不是人工圆弧。
前件仍是已通过前件；原最大0.72mm正视外圈越界按已接受决定保留。

坐标
X左右，Y往后为正，BTTF正中前表面Y=0；Z下沿=0、名义上沿=55.2。
原Normal网格尺寸142.313301×147.070330×55.175675。
头模为原比例 NIOSH Medium 注册试摆；没有为得到合格间隙而缩放或改位。
原BTTF镜腿与这副未缩放头模仍有侧向干涉；完整三维头模佩戴适配没有通过。
按用户批准决定，保留原镜腿内距和长度，不擅自改型。真实使用者的佩戴适配：没查。

本次要求 | 实际数值（单位mm，另标除外） | 核对口径
镜腿截短 | 左0.000／右0.000 | 保留原长度；原末端Y147.0703299
前耳片 | 高32.000，Z23.2～55.2 | 末端Y159.0703299，后伸12
前耳片竖缝 | 高26.000×宽3.000 | Z26.2～52.2；Y151.5703299～154.5703299
前件整体宽×前后×高 | {fd[0]:.6f}×{fd[1]:.6f}×{fd[2]:.6f} | 包括未截镜腿与末端耳片
前件定版体积 | 175.218941cm³ | 模型实体体积；不是切片耗料或打印重量
原镜腿直段内距参考 | 135.5289359 | Y140/Z45原直段未改，不是所有圆端的通用间距
耳片原根部圆角局部覆盖 | 约1.145 | 沿用当前耳片形状；原镜腿顶点不变
弧托宽 | 80.000，X−40～40 | 旧向头侧绕的两端删除，托端不再有穿带槽
弧托高 | 47.000，Z8.2～55.2 | 与原后件高度相同
弧托名义壁厚 | 2.500 | 原距离层1与3.5mm；实际新网格最薄精确值没查
弧托网格厚度下限 | ≥2.474309403 | 继承旧整面连续距离证明，裁切子集不会使最小值减小
弧托内面到头模：全部顶点 | {head['actual_vertex_min_mm']:.9f}～{head['actual_vertex_max_mm']:.9f} | 独立量全部15,673个顶点及新裁界点
弧托内面到头模：连续整面界限 | {bound[0]:.9f}～{bound[1]:.9f} | 0～2通过；这是整面保守界限，不是实际极值
弧托内面到头模：整面真实极值 | 没查 | 不把顶点极值冒充整面极值
连接竖肋 | 两道；各厚3.000、高47.000 | 左X−40～−37；右X37～40；从托壁连到盒前壁
中央直接并接 | X−4～4，Z51.2～55.2 | 局部8×4连接区域；原最近0.055563mm缝已补上
旧桥接填实 | 已取消 | 只保留两肋与中央局部连接，其他空当保留
盒子保持 | 与上一版文件字节及几何完全一致 | 原盒不移位，凸点和接口豁口原样保留
盒内腔宽×前后×深 | 117.600×15.600×45.000 | 壁与底2；上面敞开
盒外尺寸 | 121.600×19.600×47.000 | Y203.3～222.9，Z8.2～55.2
充电宝占位 | 117.000×15.000×47.000 | 插到底后上露2.000
口沿内侧凸点 | 向内0.800；宽2.000、高1.600 | 最窄喉口14.800，15厚占位要局部弹性退让0.200
凸点实际插拔与防滑 | 没查 | 盒与凸点保持上一版，不冒充刚性插拔通过
接口豁口 | 宽11.000×向下深35.000 | Z20.2～55.2；真实充电宝接口对位没查
盒侧耳板 | 厚3.000、高32.000 | 右X65.3～68.3，左对称；Y200.3～211.3
盒侧竖缝 | 高26.000×宽3.000 | Z26.2～52.2，Y203.3～206.3；沿X穿透
后脑件整体宽×前后×高 | {dims[0]:.6f}×{dims[1]:.6f}×{dims[2]:.6f} | 整体包络，包括两侧穿带耳板
后脑件范围 | X−68.3～68.3，Y179.341604427～222.9，Z8.2～55.2 | 是总包络，不是局部壁厚
后脑件实体体积 | {volume:.9f}cm³（45637.093981647mm³） | 闭合实体，1个连通体
与旧后件体积相比 | 123.814152→{volume:.6f}cm³，减{report['rear_solid_volume_reduction_vs_old_percent']:.4f}% | 实体几何体积，实际切片重量没查
带宽 | 25.000 | Z26.7～51.7；槽上下各余0.5
左带悬空段 | {ls['free_centerline_length_mm']:.9f} | 从前耳片后缘到后槽外侧前缘；40～60通过
右带悬空段 | {rs['free_centerline_length_mm']:.9f} | 同上；40～60通过
前耳片上支承带段 | 左右各4.500 | 沿耳片外表面；不计入悬空段
槽到槽带路径 | 左{ls['slot_to_slot_centerline_length_mm']:.9f}／右{rs['slot_to_slot_centerline_length_mm']:.9f} | 含耳片支承段，穿槽尾长不计
弧托/竖肋到完整25宽带面 | 最近{min_gap:.3f} | 已量到实际网格见证点并与全局下限吻合；满足至少3
弧托/竖肋到悬空25宽带面 | 最近28.300 | 同一连续整面实测；盒侧耳板属于允许接触的穿带位置
前件与后件实体重叠 | {overlap:.6f}mm³；交集为空 | 使用最终前3MF回读逆旋转模型和实际后预览实体
前后件全体Y分离下限 | 20.271274527 | 后件最前Y减前件最后Y；真实最近距离没查
悬空带和前/后实体交集 | 均为空，体积0 | 全25宽展示带核查
完整穿槽带和前/后件 | 只有允许的零体积表面接触 | 不称交集Empty；数值误差−2.27e−13mm³视为0
带面到头模最近距离 | 悬空段6.424051230；完整路径1.100484 | 连续三角面最近距离，已查无头表面交叉

带长定义
以上带长是零厚度贴面路线在带宽中线上的佩戴几何长度，不包含穿槽、回折和缝合尾段。
图中向外显示0.8mm带厚只为看清走向，真实松紧带厚度、弯折半径、未拉伸裁剪长度：没查。

前件保留值
相机占位89.94×30×25、下倾20°；实际相机细节/外形公差与实物装配没查。
X±44.97；中剖面后下(Y,Z)=(-0.8,23.6)、前下=(-24.292315520,15.049496417)、
前上=(-34.552919819,43.240275040)、后上=(-11.060604300,51.790778623)。
相机腔90.54宽×30.8高×25光轴深；左右和顶0.3、底0.5。
名义方块相机沿光轴连续推进/退出路径已核无实体阻塞；实际完整壳形与实物插拔没查。
最前Y=-35.342919819，相对BTTF正中前面35.342919819；竖直前面前移0.79。
前上封边法向厚2.009805476；鼻道总宽30；原核新增Y<0实体到鼻子最小距2.188857611。
M2底孔直径1.7，X0，离相机背面光轴12.5，轴垂直相机顶面；后顶出孔直径4。
取消的主板、外罩、盖板、USB预留与装饰孔：本版不建。

打印方向与支撑（实际切片没查）
前件：3MF已将Z55.2顶平面朝下并放到平台；相机腔悬空顶棚需要支撑，从前开口拆出。
前件按低填充切片，不按实心打印。175.218941cm³按1.24g/cm³是假设实心217.27g。
实际耗料和重量由外壁、顶底、填充及支撑共同决定，不能直接按填充率乘217g。
本3MF只包含几何和打印朝向，不表示已配置低填充参数；实际切片重量没查。
M2×10，孔口到相机名义顶面沿螺丝轴8.17764554；压到底面0.5间隙后8.67764554。
轻触固定，不以螺丝头贴壳为终点；实物锁紧没查。
后件：Z8.2底面朝下、盒口朝上；弧托内侧局部悬伸区域需要支撑，盒内保持空。
后件盒侧耳板及连接根桥底面也需要支撑：打印高度15处开始，向盒侧外挑7.5。
3mm槽顶桥接；实际桥接、0.8凸点打印表现、支撑拆除、材料强度和实物插拔：没查。
{rear_delivery}

检查来源
front/verification.json：毫米单位、密闭单体、打印方向、原Normal输入与通过版一致、生成脚本独立运行。
audit/rear_and_straps_audit.json：实际后网格与最终前3MF回读、整面接触间隙、带路径和碰撞。
measured_values.json：本次所有输入与核对数值的合并记录。
rear/verification.json：后件打印文件回读与批准实体一致性；生成包的独立重跑（文件存在时）。
'''
(ROOT/'actual_values.txt').write_text(text,encoding='utf8')
print(json.dumps({'rear_dimensions_mm':dims.tolist(),'rear_solid_volume_cm3':volume,
                  'volume_reduction_percent':report['rear_solid_volume_reduction_vs_old_percent'],
                  'audit_keys':list(audit)},indent=2))
