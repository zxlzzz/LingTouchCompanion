"""Add measured labels to the three actual assembly images."""
from pathlib import Path
import json
from PIL import Image,ImageDraw,ImageFont

P=Path(__file__).resolve().parent;W=P/'views'
g=json.loads((P/'geometry/geometry_values.json').read_text())
a=json.loads((P/'audit/surface_clearance_audit.json').read_text())
ink='#253745';blue='#3169ae';purple='#8060a2'
def font(n):return ImageFont.load_default(size=n)
def lines(d,xy,texts,size=23,color=ink,gap=43):
    x,y=xy
    for text in texts:
        text=text.replace('−','-').replace('≤','<=').replace('≥','>=')
        d.text((x,y),text,font=font(size),fill=color);y+=gap
def canvas(title,h=1450):
    im=Image.new('RGB',(1600,h),'white');d=ImageDraw.Draw(im)
    d.text((40,20),title,font=font(36),fill=ink)
    d.text((40,77),'后脑检查版｜前件与头模摆位不变；佩戴朝向，未旋转到打印平台。单位 mm。',font=font(22),fill=ink)
    x=40
    for color,label in [('#849097','原 BTTF'),('#128b9d','现有前件'),(purple,'新后脑件'),(blue,'25 宽带子'),('#c9a537','圆柱电池占位'),('#b5bbb8','原头模')]:
        d.rectangle((x,121,x+19,140),fill=color);d.text((x+27,116),label,font=font(21),fill=ink)
        x+=int(font(21).getlength(label))+53
    return im,d
vol=g['rear']['volume_mm3']/1000
L=g['strap_paths']['left']['free_length_mm'];R=g['strap_paths']['right']['free_length_mm']
lo,hi=a['rear_inner_surface']['continuous_surface_distance_bound_mm']

im,d=canvas('01  前视｜前件保留，后脑换成圆柱电池侧插盒',1550)
im.paste(Image.open(W/'front_raw.png').convert('RGB').resize((1180,770)),(10,170))
lines(d,(1220,250),['后盒总宽 93','总深 35.4','总高 32',f'实体 {vol:.3f} cm³','弧托宽 40','盒中心 Z=39.2'],23,gap=52)
im.paste(Image.open(W/'rear_iso.png').convert('RGB').resize((730,569)),(30,960))
lines(d,(810,1015),['小图单独显示新后脑件：',
    '一片短弧托＋空心盒＋两道竖肋。',
    '内腔 91×23.4×23.4；壁 2。',
    '电池 Ø22.8×90.4，轴线沿 X。',
    '+X 敞开，接口端朝开口；端面缩进 0.6。',
    '黄色为圆柱占位，未复刻真实 USB 接口。',
    '穿带板位于盒前，不挡开口。'],23,gap=49)
im.save(P/'01_front.png')

im,d=canvas('02  侧视｜盒子与带子同中心高度，开口无遮挡')
im.paste(Image.open(W/'side_raw.png').convert('RGB'),(50,170))
lines(d,(45,1130),[f'悬空带长：左 {L:.3f}／右 {R:.3f}，均在 40～60；前件不截短。',
    f'弧托整面距头保证在 {lo:.3f}～{hi:.3f} 内；这是一整个三角面的保守界。',
    f'后脑件到头模连续最近 {a["rear_head_continuous_minimum"]["distance_mm"]:.3f}，无相交。',
    '电池沿 +X 整机退出；除弹片钩外，与后件、带子、前件交叠体积均为 0。',
    '打印：-X 封闭端朝下，+X 开口朝上；外部支撑说明见数值表。'],23,gap=48)
im.save(P/'02_side.png')

im,d=canvas('03  俯视｜带子斜向较窄的盒端，弧托仅保留中段',1580)
im.paste(Image.open(W/'top_raw.png').convert('RGB').resize((1215,1035)),(210,170))
paths=g['strap_paths']
def pixel(x,y):return (210+1215/2+x*1215/320,170+1035/2-(y-96)*1215/320)
for side,row in paths.items():
    p=pixel(*row['free_start_xyz_mm'][:2]);q=pixel(*row['free_end_xyz_mm'][:2])
    d.line([p,q],fill=blue,width=4)
    for xx,yy in [p,q]:d.ellipse((xx-5,yy-5,xx+5,yy+5),fill=blue)
lines(d,(25,300),['图上方是后方','弧托宽 40','两个竖肋厚 3','正中薄舌厚 2','空当没有填实'],22,gap=50)
lines(d,(1300,650),[f'左 {L:.3f}',f'右 {R:.3f}','带宽 25','前件未改'],22,color=blue,gap=49)
im.paste(Image.open(W/'rear_top.png').convert('RGB').resize((560,381)),(25,1190))
lines(d,(635,1270),['小图为后脑件俯视，不放电池，能看清弧托与盒之间的空气。',
    '两侧穿带板厚 3、高 32，竖缝 26×3；板不超出盒端。',
    '右侧 +X 开口；左侧 -X 封闭。板根 R2 圆角仅减料。',
    '全局融合最大厚度、切片与弹片实物行为：没查。'],22,gap=49)
im.save(P/'03_top.png')

sheet=Image.new('RGB',(2400,2200),'#e9edef');d=ImageDraw.Draw(sheet)
for i,name in enumerate(['01_front.png','02_side.png','03_top.png']):
    image=Image.open(P/name).convert('RGB');image.thumbnail((1180,1060))
    x=10+(i%2)*1200;y=10+(i//2)*1100
    sheet.paste(image,(x+(1180-image.width)//2,y))
lines(d,(1240,1240),['新后脑检查版','93×35.4×32 mm',f'实体 {vol:.3f} cm³',
    f'自由带 {L:.3f}／{R:.3f}',f'托距头保证 {lo:.3f}～{hi:.3f}',
    '前件／头模／镜腿保持','电池沿 +X 退出','仅交检查版，待确认'],32,gap=80)
sheet.save(P/'Review_Three_Views.png')
print('Three labeled views and a contact sheet saved.')
