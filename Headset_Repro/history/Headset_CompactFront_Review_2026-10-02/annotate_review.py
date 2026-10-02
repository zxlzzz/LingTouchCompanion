from pathlib import Path
import json
from PIL import Image,ImageDraw,ImageFont
P=Path(__file__).resolve().parent;W=P/'views'
F=None;ink='#253745';teal='#128b9d';red='#b53c37'
g=json.loads((P/'geometry/geometry_values.json').read_text());s=json.loads((P/'audit/solid_checks.json').read_text());c=json.loads((P/'audit/clearances.json').read_text())
def font(n):return ImageFont.load_default(size=n)
def lines(d,xy,texts,size=23,color=ink,gap=43):
 x,y=xy
 for t in texts:
  d.text((x,y),t.replace('−','-').replace('≤','<=').replace('≥','>='),font=font(size),fill=color);y+=gap
def canvas(title,height=1430):
 im=Image.new('RGB',(1600,height),'white');d=ImageDraw.Draw(im)
 d.text((40,20),title,font=font(34),fill=ink)
 d.text((40,73),'检查版｜相机后退3.62；原头模、镜腿耳片、Carbon6K后脑及带子位置不动。单位mm。',font=font(21),fill=ink)
 x=40
 for col,label in [('#849097','BTTF原件'),(teal,'新增薄壁'),('#e49333','相机占位'),('#b5bbb8','原头模'),('#8060a2','后脑件'),('#3169ae','带子')]:
  d.rectangle((x,121,x+19,140),fill=col);d.text((x+27,116),label,font=font(21),fill=ink);x+=int(font(21).getlength(label))+56
 return im,d
im,d=canvas('01  前视｜中部去掉下方双腔，原件鼻缺口保留')
raw=Image.open(W/'front_detail.png').convert('RGB');raw.thumbnail((1500,820));im.paste(raw,((1600-raw.width)//2,180))
im.paste(Image.open(W/'front_raw.png').convert('RGB').resize((500,326)),(45,1010))
lines(d,(590,1000),['镜头窗内口68×20、外口72×24，45°倒角。',
 '灰色下部是保留的BTTF原件，不是新增底板。',
 '相机区平顶：内55.14／外57.14，厚2。',
 f'前件实体{g["volume_cm3"]:.3f}cm³；新壳常规板面厚2。',
 'STP到带壳整机的配准：没查；橙色不是实际镜头。'],23,gap=48)
im.save(P/'01_front.png')
im,d=canvas('02  侧视｜新中部前伸缩短，两翼仍保留旧位置')
im.paste(Image.open(W/'side_raw.png').convert('RGB'),(50,165))
lines(d,(45,1120),['中部最前33.485，满足34；整件最前37.024，来自沿用两翼，超3.024。',
 '相机区最高Z=57.14，满足57.5；两翼与耳片不高于55.2。',
 f'相机到位离头模最近{c["camera_head"]["distance_mm"]:.3f}；新增前侧实体离鼻{c["nose_Ynegative_new_material"]["distance_mm"]:.3f}。',
 '中部宽×高×前后：94.54×43.886×47.977。',
 '装入路径：下按可通过，水平推进撞保留原料；详见X=30图内红色补充剖面。'],23,gap=46)
im.save(P/'02_side.png')
im,d=canvas('03  俯视｜镜腿耳片不动，后脑件沿用Carbon6K',1530)
im.paste(Image.open(W/'top_raw.png').convert('RGB').resize((1242,1058)),(200,165))
lines(d,(50,1260),['整件宽142.313，与BTTF原宽相同；镜腿截短0。',
 '耳片高32，竖缝26×3；带子悬空段左46.303／右46.308。',
 '后脑件93×35.4×32，实体23.634cm³，本次没有重做。',
 '检查3MF保持佩戴方向；仍有不满足项，不是打印定版。'],24,gap=47)
im.save(P/'03_top.png')
for x,title in [(0,'04  正中剖面｜取消下方封底和双腔'),(30,'05  X=30剖面｜底壁弹片；附两端推进碰撞局部')]:
 im,d=canvas(title,1550);im.paste(Image.open(W/f'section{x}_true.png').convert('RGB'),(0,160))
 if x==0:
  texts=['前壁从相机底壁外下沿起，不延到Z=0；底壁下方只保留灰色原件。',
   '平顶内55.14、厚2；前上方斜面离整个下按圆弧至少0.3。',
   '橙色虚线是放平到位，紫线是前上角轨迹；装入过程先向前平推，再下按。',
   '图只画真实剖切轮廓；两端水平推进碰撞不在正中剖面内。']
 else:
  texts=['底壁厚2、底间隙0.5；弹片X=±30，长8、宽6、U缝0.6，小钩0.8。',
   '左上补充X=44剖面：红色是距水平停止位置后10mm时的真实交叠。',
   '完整水平扫掠撞原件11.498mm³；阻挡台阶比平放底面高1.263。',
   '该原料按要求保留，未为装入路径删掉；整个20°下按过程通过。']
 lines(d,(45,1345),texts,22,gap=45);im.save(P/f'0{4 if x==0 else 5}_section{x}.png')
sheet=Image.new('RGB',(2400,3220),'#e9edef');d=ImageDraw.Draw(sheet)
names=['01_front.png','02_side.png','03_top.png','04_section0.png','05_section30.png']
for i,name in enumerate(names):
 im=Image.open(P/name).convert('RGB');im.thumbnail((1180,1040));x=10+(i%2)*1200;y=10+(i//2)*1060;sheet.paste(im,(x+(1180-im.width)//2,y))
lines(d,(1240,2200),['压小检查版',f'前件实体{g["volume_cm3"]:.3f}cm³','最高57.14，通过',
 '中部最前33.485，通过','整件最前37.024，未通过','水平推进撞原件，未通过',
 '下按20°、鼻距、相机头距通过','光学实装配准没查','逐条数值及打印见附表'],32,gap=82)
sheet.save(P/'Review_Five_Views.png')
print('Five CAD views labeled and montage saved.')
