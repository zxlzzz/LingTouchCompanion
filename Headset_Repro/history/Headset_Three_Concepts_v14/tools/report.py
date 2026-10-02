from pathlib import Path
import json,math,html,zipfile,numpy as np
from PIL import Image,ImageDraw,ImageFont
P=Path(__file__).parent.parent
styles={'A':('包覆面罩','眉额与面侧接触垫＋后脑带','Hicks 等，2013 年深度导航滑雪镜样机','https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0067695','完整不透光包覆面，内外两层围合。由面侧垫与后带承重，正面只有相机开口。覆盖最多，也最重。'),'B':('开放眼镜框','鼻托＋耳上镜腿＋后脑带','Envision Glasses','https://support.letsenvision.com/hc/en-us/articles/7604953925777-Hardware-Form-and-Design','保留鼻托、空镜框和耳上镜腿，眼前开放。右侧为分体器件盖；相机置于眉框上方。三者中结构最轻，但鼻梁和耳上负担最大。'),'C':('头顶承重头箍','头顶垫＋两侧垫＋后脑带','RealWear Navigator 520 Overhead Band','https://shop.realwear.com/products/overhead-band','顶部弓形带承担主要重量，额前悬挂相机，两侧高置器件。眼前与鼻梁开放；头顶高度更大。')}
data={}
for k in styles:
 d=P/k;data[k]={n:json.loads((d/(n+'.json')).read_text(encoding='utf-8')) for n in ['specification','checks','design_data','routes','fasteners']}
def dims(v):return ' × '.join(f'{x:.1f}' for x in v)
def link(u,t):return f'<a href="{html.escape(u,quote=True)}">{html.escape(t)}</a>'
def table(head,rows):return '<div class="scroll"><table><thead><tr>'+''.join(f'<th>{x}</th>' for x in head)+'</tr></thead><tbody>'+''.join('<tr>'+''.join(f'<td>{x}</td>' for x in row)+'</tr>' for row in rows)+'</tbody></table></div>'
rows=[]
for k,(name,wear,ref,url,desc) in styles.items():
 z=data[k];s=z['specification'];c=z['checks'];rmin=min(r['min_radius_mm'] for r in c['bend_checks'] if r['criterion_mm']==12)
 assert all(not hits for x in c['collisions_at_pitch'].values() for hits in x.values()),(k,'collisions')
 assert all(x['passed'] for x in c['fov_checks']) and c['continuous_fov_bound']['passed'],(k,'FOV')
 assert all(x['passed'] for x in c['bend_checks']),(k,'bend')
 assert all(p['watertight'] and p['connected_parts']==1 for p in s['parts'] if p['category']=='structure'),(k,'topology')
 rows.append([f'<a href="#{k}">{k} · {name}</a>',link(url,ref),wear,dims(s['assembly_size_mm'])+' mm',f"约 {s['estimated_total_g']:.0f} g<br><small>{s['estimated_range_g'][0]:.0f}–{s['estimated_range_g'][1]:.0f} g</small>",f"{s['mass_breakdown_g']['PETG_structure_g']:.0f} g",'通过','0°、20°通过<br>0°—20°连续范围通过',f'通过<br>USB 最小 {rmin:.2f} mm'])
summary=table(['方案','外形参考','承重与戴法','整机外形：宽×前后×高','整机估重，含电池','打印结构估重','器件干涉','深度／彩色视场','弯曲半径'],rows)
cards=''.join(f'<article><h2>{k} · {v[0]}</h2><a class="image-link" href="{k}/04_isometric.png"><img id="img{k}" src="{k}/04_isometric.png"></a><p>{v[4]}</p><p>{link(k+"/Concept_"+k+".blend","Blender 模型")}　{link(k+"/Concept_"+k+".3mf","3MF 装配")}</p></article>' for k,v in styles.items())
params=[['相机俯仰','默认 −20°；范围 −20°～0°','blend 中 MOVE__CS30 的 pitch_deg；镜头、IMU、共同支架和相应线头一起变化。'],['参考头','156 × 192 × 232 mm','近似椭球，附简化耳朵与鼻子；不是人体扫描。'],['A 贴脸层内表面','椭球半径 81 / 99 / 119 mm','相对参考头留约 3 mm 的基础余量；不能据此推断每个位置实际间隙相同。'],['外壳／内层默认壁','2.0 mm','盖板、安装底板的名义壁厚。'],['卡槽侧壁','1.6 mm','小板导槽的默认侧壁；卡扣强度待试印。'],['卡槽装配余量','单侧 0.3 mm','麦克风、功放、Splitter、IMU 的槽宽余量。'],['内层承重杆半径','主环 2.4 mm；连接杆 1.8～3.3 mm','连接内层与器件支座；局部尺寸随接点不同。'],['M2 盖板连接','M2×6；嵌件外径 3.2 mm、长 4 mm','盲孔座，螺丝从内侧进入，外观面不穿孔。'],['CS30 安装','89.94 × 30 × 25 mm；后孔横距 45 mm','带壳外形按官方尺寸图重建；后安装孔未标注的竖向基准用 ±3 mm 长槽兼容。'],['相机开口','扫掠占位外扩约单侧 0.55 mm','A 外壳开口覆盖所有允许俯仰角；前面没有透明片。'],['相机转轴','双侧 M3；轴心在相机局部 Y=0、Z=0','内外支架用铰接固定，调角后机械锁紧。'],['主板背后空气隙','最小约 3.6 mm','由当前背面器件占位至安装板的几何距离；不是温升测试。'],['弯针排针','2×20，2.54 mm；两排离板 2.5 / 5 mm','沿用 v12 已确认方向，母头平行板面；25 号没有接线母头。'],['USB 线','外径 3.0 mm；设计最小半径 12 mm','临时采用 4D 作为建模门槛。'],['单根信号线','外径 0.8 mm；设计最小半径 3.2 mm','不等于所购线束的厂商弯曲规格。'],['喇叭线','每根外径 1.1 mm；设计最小半径 4.4 mm','自带线每根保留约 120 mm；转接段独立。'],['后带','宽 25 mm；几何厚 2 mm','后脑电池托架独立穿带。'],['后带线缆余量','S 弯半径 22 mm；初始夹点距 88 mm','每根余线段长约 138.2 mm，可容纳 20 mm 的夹点分离增量。'],['电池占位','117 × 47 × 15 mm；143 g','继续用 NB10000 Gen4 候选包络，双口位置仍是估计；未改变 glass.md 采购清单。'],['打印材料估重','PETG，1.27 g/cm³','以净实体体积估算；实际耗材密度、切片和支撑会改变用量。']]
params += [['A 贴脸软条','直径 4 mm；眉额 Z=54 mm、面侧 Z=-8 mm','软条沿贴脸层内表面设置，下侧中央避开鼻梁缺口。'],['B 鼻托／耳上垫','鼻托 7×6.4×14 mm；耳垫 10×24×7 mm','连接内层支杆并与参考鼻侧、耳朵上沿接触；软垫接触压缩有意允许。'],['C 头顶／侧垫','头顶 42×27×13.5 mm；侧垫 15×34×26 mm','头顶和两侧同时接触承力弓与参考头，减轻鼻梁承重。'],['供电双线软袖套','88×5.2×65 mm；两侧布面 0.6 mm','共用一个双面袖套，端部开口；需选可随头带至少伸长约23%的软织物。']]
parameterdata=[dict(parameter=x[0],default=x[1],purpose=x[2]) for x in params]
(P/'parameters.json').write_text(json.dumps(parameterdata,ensure_ascii=False,indent=2),encoding='utf-8')
sections=''
for k,(name,wear,ref,url,desc) in styles.items():
 z=data[k];s=z['specification'];c=z['checks'];d=z['design_data'];r=z['routes'];mass=s['mass_breakdown_g']
 contacts=json.loads((P/k/'contact_checks.json').read_text());assert all(p['intersects_reference_head'] and p['intersects_carrier'] for p in contacts)
 groups=[]
 for label,criterion in [('USB 与供电线',12),('信号线',3.2),('喇叭线',4.4)]:
  minimum=min(x['min_radius_mm'] for x in c['bend_checks'] if x['criterion_mm']==criterion);groups.append([label,f'{criterion:.2f} mm',f'{minimum:.2f} mm','通过'])
 connectors=[]
 for n,v in r.items():
  a=d['leads'][v['a']]['point'];b=d['leads'][v['b']]['point'];direct=float(np.linalg.norm(np.array(a)-b));clen=s['wire_lengths_mm'][n];mn=min(x['min_radius_mm'] for x in c['bend_checks'] if x['name']==n)
  connectors.append([n,html.escape(v['a'].replace('LEAD__','')),html.escape(v['b'].replace('LEAD__','')),f'{direct:.1f}',f'{clen:.1f}',f'{mn:.2f}'])
 moves=[]
 namemap={'CS30':'相机','ICM42688P_LogicalEdges':'IMU','Radxa_ZERO_3W':'主板','Heatsink_5519A':'散热片','INMP441':'麦克风','MAX98357A':'功放','USB_C_PWR_Splitter':'Splitter','Speaker_27859':'左喇叭','Speaker_PH125_pair':'喇叭接头','Battery_NB10000_PLACEHOLDER':'后脑电池'}
 for n,p in d['poses'].items():
  if 'OPTION' in n:continue
  v=p['translation_mm'];moves.append([namemap.get(n[6:],n),*(f'{q:+.1f}' for q in v),f'{np.linalg.norm(v):.1f}'])
 drawings=''.join(f'<a href="{k}/{f}.png"><img loading="lazy" src="{k}/{f}.png"><span>{label}</span></a>' for f,label in [('01_front','前视'),('02_right','右侧'),('03_top','俯视'),('04_isometric','斜视')])
 largest=sorted([p for p in s['parts'] if p['category']=='structure'],key=lambda q:q['volume_mm3'],reverse=True)
 prints=table(['打印对象','原装配坐标包络 mm','建议朝向／支撑'],[[p['name'],dims(p['dimensions_mm']),('底缘朝床；顶部内侧跨空、开口上沿和盲孔座需要支撑，支撑尽量从内侧接触。' if p['name'].startswith('OUTER__Opaque') else '正面朝床，保持侧面与顶部弓形件整件；安装台阶、横向卡槽、耳部悬臂及线夹需要支撑。' if p['name']=='INNER__Main_load_carrier' else '支架背面或盖板平面朝床；卡扣倒钩、横孔与盲孔边缘局部支撑。') ] for p in largest[:7]])
 sections+=f'''<section id="{k}"><div class="eyebrow">方案 {k}</div><h2>{name}</h2><p>{desc} 参考：{link(url,ref)}。只借鉴其戴法与外形组织，不继承原产品尺寸、重量或性能。</p><div class="gallery">{drawings}</div>
<p class="files">{link(k+'/Concept_'+k+'.blend','下载 .blend')}　{link(k+'/Concept_'+k+'.3mf','下载 3MF')}　{link(k+'/checks.json','完整检查记录')}　{link(k+'/specification.json','尺寸与重量明细')}</p>
<h3>实际检查</h3><p>在 0° 和 20° 两个姿态，器件之间、器件与结构、器件与参考头均未检出干涉；附加检查的线束与其他器件、线束与参考头也未检出干涉。相同器件内部的装配接触、散热片与主板的接触，以及紧固件配合不计作错误。承重软垫另行确认了与内层和参考头的接触，软垫的预压接触是有意保留的；实际接触压力未检查。{link(k+'/contact_checks.json','软垫接触记录')}</p>
<p>深度 100°×75°、彩色 97°×95.5°：0°、20°均通过。另逐度计算了 21 个姿态、42 个视场，并用运动对象的后光学平面与曲线控制点极值，确认整个 0°—20° 连续区间无遮挡。</p>
{table(['线类','采用的门槛','21 个姿态中的实算最小值','结果'],groups)}
<p>两根后带供电线各有电池侧、镜体侧固定夹。每根 S 形余线约 {r['POWER_1']['service_loop']['initial_length_mm']:.1f} mm；夹点分离增加 20 mm 时，该段计算最小半径 {r['POWER_1']['service_loop']['minimum_radius_at_full_extension_mm']:.2f} mm，仍大于 12 mm。中段放在可随带伸展的软袖套里；两端没有用刚性杆连成一体。</p>
<details><summary>接口直线距离、实际曲线长度与弯曲结果</summary><p>单位 mm，均为默认下倾 20°。直线距离用于比较器件远近，实际曲线长度才接近所需线长；还未加入采购时的装配余量。共享时钟 12、35 在同一母头端分支，不额外增加主板针位。</p>{table(['连接','起点','终点','直线距离','曲线长','最小半径'],connectors)}</details>
<details><summary>相对 v12 的器件移动量</summary><p>三个戴法重新分配了承重位置，因此相机与侧面器件随结构移动。下表为世界坐标：+X 戴者右侧、+Y 向前、+Z 向上。IMU 始终与相机刚性绑定；官方 STEP 网格本体未修改。</p>{table(['器件','ΔX mm','ΔY mm','ΔZ mm','移动距离 mm'],moves)}</details>
<details><summary>重量、打印与模型边界</summary><p>整机估计 <b>{s['estimated_total_g']:.0f} g</b>，估计范围 {s['estimated_range_g'][0]:.0f}–{s['estimated_range_g'][1]:.0f} g，其中打印结构 {mass['PETG_structure_g']:.0f} g。74 g 相机、143 g 电池引用厂商重量；其余器件、插头、软带和紧固件为估算。散热块按当前 55×19×2 mm 实心铜占位估算 {mass['heatsink_solid_copper_estimate_g']:.1f} g。不是称重结果，也不是统计置信区间。</p>
<p>采用 PETG、默认 2 mm 壁。所有打印结构网格都已核对闭合，各自是一个连通实体。3MF 包含 {s['mesh_objects']} 个具名网格对象，保留壳、器件、插头、线和带的独立名称；它是装配文件，不能把其中的电池、电子器件和线缆一起当成塑料件打印。参考头只保留在 blend 中。</p>
{prints}<p>上述壳件按建议朝向的床面包络均可放入 256×256 mm；未实际切片、未试印。支撑用量不包含在净结构重量内。材料卡扣疲劳、局部壁厚全场扫描、声音、温升、佩戴压力及实物装配均为<b>未检查</b>。</p></details></section>'''
body=f'''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>三种戴法 · v14 方案对比</title><style>
*{{box-sizing:border-box}}html{{scroll-behavior:smooth}}body{{margin:0;background:#edf1f4;color:#172a35;font:16px/1.65 "Microsoft YaHei",sans-serif}}header{{background:#172a35;color:#fff;padding:40px 5vw 32px}}header p{{color:#d2dbe1;max-width:1050px}}h1{{font-size:34px;margin:4px 0}}h2{{font-size:25px;margin:5px 0 18px}}h3{{margin-top:24px}}.eyebrow{{letter-spacing:3px;font-size:13px;opacity:.8}}main{{max-width:1600px;margin:auto;padding:24px}}section{{background:#fff;padding:28px;border-radius:14px;margin:26px 0}}.cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}}article{{background:#fff;padding:18px;border-radius:14px}}article h2{{font-size:22px}}img{{display:block;width:100%;border-radius:8px}}a{{color:#176f85;text-decoration:none}}a:hover{{text-decoration:underline}}.tabs{{display:flex;gap:12px;margin:5px 0 20px;flex-wrap:wrap}}button{{border:1px solid #bbc9d0;background:#fff;color:#18333e;padding:10px 20px;border-radius:30px;font:inherit;cursor:pointer}}button.active{{background:#18333e;color:white}}.scroll{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;font-size:14px}}th,td{{text-align:left;vertical-align:top;padding:12px 13px;border-bottom:1px solid #dde4e8;min-width:85px}}th{{background:#edf3f6}}small{{color:#607580}}.note{{border-left:4px solid #b78b4f;background:#faf5ea;padding:14px 18px;margin:18px 0}}.gallery{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px}}.gallery span{{display:block;text-align:center;font-size:14px;color:#546b78}}details{{border:1px solid #dce5e9;border-radius:8px;padding:15px;margin-top:16px}}summary{{font-weight:bold;cursor:pointer}}footer{{padding:35px;color:#586c78}}@media(max-width:900px){{.cards{{grid-template-columns:1fr}}.gallery{{grid-template-columns:1fr 1fr}}main{{padding:12px}}section{{padding:18px}}}}
</style><header><div class="eyebrow">LINGTOUCH · HEADSET STUDIES · V14</div><h1>三种戴法，同一套器件</h1><p>面罩、眼镜框、头顶头箍。基于 v12 已确认的器件与弯针布局重新建立三种承重结构。相机默认下倾 20°；电池独立固定在后脑带上。三种方案都实际建立了完整装配和线束，并执行几何检查。</p></header><main>
<div class="tabs"><button class="active" onclick="view('04_isometric',this)">斜视对比</button><button onclick="view('01_front',this)">前视对比</button><button onclick="view('02_right',this)">右侧对比</button><button onclick="view('03_top',this)">俯视对比</button></div><div class="cards">{cards}</div>
<section><h2>方案对比</h2>{summary}<p>尺寸包含后脑电池、托架、软带、线与固定夹，不含参考头。渲染图各自居中取景，尺寸比较请以表格为准。</p><div class="note"><b>重量没有压到 300 g。</b>这三种方案保留了全部器件与可拆卸打印结构。相机和电池合计已约 217 g；最终估重应看整机数，不能用外壳重量代替。B 最轻，C 将负担移到头顶，A 的完整包覆代价最大。</div>
<p><b>供电接口仍有一个未定项：</b>glass.md 的目标是单 Type-C 入口后再向主板和相机供电，但内部成品分配方案尚未确定。本次沿用此前授权的“两根供电线从后脑进入镜体”的机械占位，用现有候选电池的两个估计出口定位两端夹具；这不是已经确认的双口供电接线方案。没有添加待定分配板，也没有修改 glass.md。电气供电闭合性：<b>未检查</b>。</p>
<p>弯曲半径门槛采用 USB 12 mm、信号 3.2 mm、喇叭单线 4.4 mm，都是在具体线材未定时的建模标准。已计算实际曲线是否达到这些值；是否符合最终所购线缆的厂商限制：<b>未检查</b>。线与线之间的接触／交叠没有作为本轮三项检查的合格依据。</p></section>
{sections}<section><h2>参数与固定方式</h2><p>相机俯仰可以在 blend 中直接调整；其余下表为建模参数，改变后需要重新生成相应结构并复查。场景属性中的尺寸提示不代表所有网格都会自动重建。</p>{table(['参数','默认值','作用'],params)}
<p>所有非电池器件的支座属于内层：Radxa 对应官方模型四个安装孔；CS30 后安装孔对应的支架同时固定 IMU；小板用导槽和弹性限位；左喇叭声口朝左耳。外盖拆下后器件由内层继续保留。A 的麦克风有朝贴脸侧的短声道与垫圈槽，B/C 底部开口直接开放；右侧散热面保留通风缝。没有采用胶粘固定。</p>
<p>CS30 的官方 STEP 内部几何和 Radxa 官方 STEP 几何保留。新的带壳 CS30 是依据官方尺寸图重建的占位，不能称为厂家提供的成品外壳 STEP；它已作为独立具名对象导出到三个 3MF。</p></section>
<section><h2>资料来源与检查边界</h2><p>{link('https://wiki.dfrobot.com/sen0673/','DFRobot SEN0673 wiki')}用于本轮指定的两路视场角。其彩色垂直视场 95.5° 与旧资料中的 59.5° 不同，本轮遵照用户指定的 wiki 采用较大的 95.5°。</p><p>{link('https://dfimg.dfrobot.com/wiki/17502/SEN0673_rgbd-depth-camera_datasheet_V1.0.pdf','CS30 官方尺寸与重量图')}：89.94×30×25 mm、74 g、后安装孔横距 45 mm；成品 USB 口在端面，本次修正了 v12 的下侧接口占位。{link('https://www.nitecore.com/product/nb10000gen4','NB10000 Gen4')}用于候选重量143 g，外壳继续留原有117×47×15 mm包络。{link('https://help.prusa3d.com/article/petg_2059','PETG 材料说明')}作为打印材料参考，1.27 g/cm³为估重假设。</p><p>检查证明的是这些估计几何在当前参数下的关系。Splitter、小板、插头、电池出口以及相机孔的未标注竖向基准仍待实物确认；参考头是近似模型。没有做有限元、热仿真、声学测试、电气联合运行、线材寿命、实际切片或人体试戴。</p></section></main><footer>文件中的坐标单位为 mm。完整几何检查记录保留在每个方案的 checks.json；尺寸、物料估重和封闭网格结果保留在 specification.json。</footer><script>function view(n,b){{for(let k of ['A','B','C']){{let x=document.getElementById('img'+k);x.src=k+'/'+n+'.png';x.parentElement.href=x.src}}document.querySelectorAll('button').forEach(x=>x.classList.remove('active'));b.classList.add('active')}}</script></html>'''
(P/'三个方案对比.html').write_text(body,encoding='utf-8')
fontfile=None;fnt=ImageFont.load_default(size=30);small=ImageFont.load_default(size=22);im=Image.new('RGB',(1800,730),'#edf1f4');draw=ImageDraw.Draw(im)
for i,(k,(name,wear,*_)) in enumerate(styles.items()):
 x=i*600;pic=Image.open(P/k/'04_isometric.png').convert('RGB');pic.thumbnail((590,510));im.paste(pic,(x+(600-pic.width)//2,60));s=data[k]['specification'];draw.text((x+20,16),k+'  '+name,font=fnt,fill='#172a35');draw.text((x+20,575),wear,font=small,fill='#172a35');draw.text((x+20,615),dims(s['assembly_size_mm'])+' mm',font=small,fill='#526772');draw.text((x+20,655),f"含电池约 {s['estimated_total_g']:.0f} g  |  三项几何检查通过",font=small,fill='#526772')
im.save(P/'对比总览.png')
readme='先打开「三个方案对比.html」，顶部可切换前、右侧、俯、斜视对比。\nA：包覆面罩；B：开放眼镜框；C：头顶承重头箍。\n每个文件夹有一个 blend、一个 3MF、四张 PNG、检查记录、尺寸重量数据和原始走线参数。\n3MF 是完整具名装配，不是将所有对象一起打印的文件；电池、器件、线缆均为实际占位。\n相机默认下倾20度，在 blend 中调 MOVE__CS30 的 pitch_deg（-20 到0）；其余生成参数见 parameters.json。\n三项检查已实际运行，范围与未检查项写在对比页。所有重量是估算，含电池；未达到300g。\n内部单口供电分配方案在 glass.md 中仍未定，本次只落实两条供电通路的机械占位与固定，不新增待定电气器件。\n'
(P/'交付说明.txt').write_text(readme,encoding='utf-8-sig')
print('REPORT GENERATED',flush=True)
