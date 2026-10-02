"""Label actual measured CAD views; combine five images for quick review."""
from pathlib import Path
import json
from PIL import Image,ImageDraw,ImageFont

P=Path(__file__).resolve().parent;W=P/'views'
G=json.loads((P/'geometry/geometry_values.json').read_text(encoding='utf8'))
F=None;ink='#253745';teal='#128b9d';red='#b53c37'
def font(n):return ImageFont.load_default(size=n)
def lines(d,xy,texts,size=23,color=ink,gap=41):
    x,y=xy
    for text in texts:
        text=text.replace('−','-').replace('≤','<=').replace('≥','>=')
        d.text((x,y),text,font=font(size),fill=color);y+=gap
def canvas(title,height=1370):
    im=Image.new('RGB',(1600,height),'white');d=ImageDraw.Draw(im)
    d.text((40,20),title,font=font(36),fill=ink)
    d.text((40,74),'检查版｜佩戴坐标，未摆打印方向；相机、原件、头模及后脑位置保留。单位 mm。',font=font(21),fill=ink)
    x=40
    for color,label in [('#849097','BTTF 原件'),(teal,'新增薄壁'),('#e49333','相机占位'),('#b5bbb8','原头模'),('#8060a2','后脑件'),('#3169ae','带子')]:
        d.rectangle((x,121,x+19,140),fill=color);d.text((x+27,116),label,font=font(21),fill=ink)
        x+=int(font(21).getlength(label))+56
    return im,d
vol=G['volume_cm3'];height=G['maximum_roof_z_mm'];reach=-G['frontmost_y_mm']

im,d=canvas('01  前视｜整机藏入空心薄壳，正面只留镜头长圆窗')
im.paste(Image.open(W/'front_detail.png').convert('RGB').resize((1480,805)),(60,161))
im.paste(Image.open(W/'front_raw.png').convert('RGB').resize((500,326)),(50,1000))
lines(d,(590,1000),['窗口内侧 68×20；外侧 72×24；45° 倒角。',
    '橙色是 89.94×30×25 的带壳占位体，未画成真实镜头。',
    f'前件实体 {vol:.3f} cm³；BTTF 原件 44.289 cm³。',
    f'最高 Z={height:.3f}，超 60 限值 {height-60:.3f}。',
    '两翼维持 Z≤55.2；与中部高屋顶之间有台阶。',
    'STP 光学组件和带壳整机的坐标对应：没查。'],22,gap=43)
im.save(P/'01_front.png')

im,d=canvas('02  侧视｜原头模摆位，相机下倾 20°')
im.paste(Image.open(W/'side_raw.png').convert('RGB'),(50,170))
lines(d,(50,1120),[f'最前点 Y=−{reach:.3f}，满足不超过 37.5；下沿 Z=0。',
    '相机从贴脸侧沿光轴装入／退出；该路径除卡钩外交叠体积 0。',
    '镜腿不截；耳片高 32，竖缝 26×3；两侧带子悬空约 44.32。',
    '灰色头模保持上一版试摆；这不代表已通过实人佩戴检查。'],23,gap=45)
im.save(P/'02_side.png')

im,d=canvas('03  俯视｜前件薄壁重做，后脑件沿用已通过版',1500)
im.paste(Image.open(W/'top_raw.png').convert('RGB').resize((1242,1058)),(200,165))
im.paste(Image.open(W/'rear_iso.png').convert('RGB').resize((390,301)),(20,1180))
lines(d,(455,1250),['后脑件 136.60×43.558×47，实体 45.637 cm³。',
    '中段弧托宽 80；两道竖肋；盒子与托之间没有填实。',
    '本次两个 3MF 均保留原佩戴坐标，不平移到打印平台。'],23,gap=46)
im.save(P/'03_top.png')

for section,title in [(0,'04  正中剖面｜X=0，鼻道贯通'),(30,'05  剖面｜X=30，相机下方为空腔')]:
    im,d=canvas(title,1510)
    raw=Image.open(W/f'section{section}_true.png').convert('RGB')
    # The diagram already carries plane and axis labels; retain its exact scale.
    im.paste(raw,(0,160))
    d=ImageDraw.Draw(im)
    if section==0:
        texts=['只画切平面上的实体轮廓，空白是真正空腔；灰线是原头模表面。',
               '鼻道总宽 30；此处不做 Z=0 底板及下方前壁，原鼻托位置保留。',
               '筒顶／筒底均 2；相机顶间隙 0.3，底间隙 0.5。',
               '相机由左侧的贴脸开口沿光轴推向右前方，前脸靠住前壁内面。']
    else:
        texts=['筒底下方保留空腔；Z=0～2 是底板，没有实心填料。',
               '底壁后端是 U 缝弹片：长 8、宽 6、缝 0.6，卡钩高 0.8。',
               'U 缝让这处下腔与相机腔窄连通；不能靠该窄缝拆支撑。',
               '斜筒顶延伸到旧件后侧投影；此剖面已超过 Z=60。']
    lines(d,(45,1325),texts,22,gap=41)
    im.save(P/f'0{4 if section==0 else 5}_section{section}.png')

names=['01_front.png','02_side.png','03_top.png','04_section0.png','05_section30.png']
sheet=Image.new('RGB',(2400,3150),'#e9edef');d=ImageDraw.Draw(sheet)
for i,name in enumerate(names):
    image=Image.open(P/name).convert('RGB');image.thumbnail((1180,1010))
    x=10+(i%2)*1200;y=10+(i//2)*1040
    sheet.paste(image,(x+(1180-image.width)//2,y))
lines(d,(1240,2160),['检查版关键结果',f'前件 {vol:.3f} cm³',f'最前 {reach:.3f} ≤37.5',
    f'最高 {height:.3f} >60','屋顶高度条件尚不满足','其余逐条见数值表'],36,gap=80)
sheet.save(P/'Review_Five_Views.png')
print('Five labeled views and a contact sheet saved.')
