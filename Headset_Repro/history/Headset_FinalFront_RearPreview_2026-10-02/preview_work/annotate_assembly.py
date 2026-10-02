"""Label measured preview geometry; no artwork changes to the meshes."""
from pathlib import Path
import json
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[1]
W=ROOT/'preview_work'
R=json.loads((ROOT/'rear_work/rear_values.json').read_text())
S=json.loads((ROOT/'connection/strap_values.json').read_text())
ink='#263847';teal='#138798';purple='#8060a2';blue='#3169ae';orange='#c08337';gray='#899298'
F=None
def font(n):return ImageFont.load_default(size=n)
def lines(d,xy,items,size=23,color=ink,gap=39):
    x,y=xy
    for item in items:d.text((x,y),item,font=font(size),fill=color);y+=gap
def canvas(title,height=1370):
    im=Image.new('RGB',(1600,height),'white');d=ImageDraw.Draw(im)
    d.text((42,22),title,font=font(37),fill=ink)
    d.text((42,79),'头模沿用原比例和原试摆；前件定版，后脑件待确认。所有尺寸单位 mm。',font=font(23),fill=ink)
    x=42
    for col,label in [(gray,'头模／原 BTTF'),(teal,'前壳与前耳片'),(purple,'后脑件'),(blue,'25 宽松紧带走向'),(orange,'3 厚竖肋（小图）')]:
        d.rectangle((x,128,x+20,148),fill=col);d.text((x+28,124),label,font=font(21),fill=ink)
        x+=int(font(21).getlength(label))+54
    return im,d

im,d=canvas('01  前视｜镜腿不截，后脑改为短弧托与空桥接')
im.paste(Image.open(W/'front_raw.png').convert('RGB').resize((1050,713)),(28,177))
lines(d,(1102,220),['前耳片高度 32','竖缝 26 × 3','镜腿截短：左 0／右 0','原两腿内距保持','相机下倾 20°'],24,gap=47)
lines(d,(1102,535),['后件总宽 136.60','总深 43.558／高 47','弧托宽 80','实体 45.637 cm³'],24,gap=47)
im.paste(Image.open(W/'rear_iso.png').convert('RGB').resize((570,382)),(1005,832))
lines(d,(45,922),['后件小图：短弧托＋平盒，大片空当保留。','两道橙色竖肋厚 3，高 47；盒侧竖缝 26×3。','盒内腔 117.6×15.6×45；壁与底 2。','电池上露 2；凸点 0.8；接口豁口 11×35。','弧托整面离头模已核在 0.429～1.569（保守界限）。'],23,gap=42)
lines(d,(45,1160),['前件 3MF 已按顶面朝下摆好；相机腔顶棚需要支撑；固定螺丝 M2×10。','后件本轮只交图与数；头模配合仍为原试摆，实人佩戴与打印插拔：没查。'],22,gap=40)
im.save(ROOT/'01_front.png')

im,d=canvas('02  侧视｜带子绕过前耳片，悬空拉到盒侧')
im.paste(Image.open(W/'side_raw.png').convert('RGB'),(50,178))
lines(d,(45,1120),['悬空段：左 44.318／右 44.319；目标 40～60，均满足。','前耳片外面贴着的 4.5 不计入悬空段；槽到槽走向长约 48.82。','前后件重叠 0；托／竖肋到完整 25 宽带面最近 25.3，满足至少 3。','自由长度是佩戴位置的几何长度；松紧带未拉伸裁剪长度、实际厚度：没查。'],23,gap=42)
im.save(ROOT/'02_side.png')

im,d=canvas('03  俯视｜取消填实，保留两端竖肋和中央小连接',1500)
im.paste(Image.open(W/'top_raw.png').convert('RGB').resize((1125,900)),(240,170))
def pixel(x,y):return (240+1125/2+x*1125/350,170+900/2-(y-97)*1125/350)
for name,row in S['sides'].items():
    p=pixel(*row['free_start_xyz_mm'][:2]);q=pixel(*row['free_end_xyz_mm'][:2])
    d.line([p,q],fill=blue,width=4)
    for x,y in [p,q]:d.ellipse((x-5,y-5,x+5,y+5),fill=blue)
lines(d,(35,220),['图上方为后方','后盒保持原位','弧托只留中段','托端不再开槽','空当不再填实'],22,gap=43)
lines(d,(1356,382),['蓝线：悬空段','左 44.318','右 44.319','宽 25','前腿不截'],21,color=blue,gap=43)
im.paste(Image.open(W/'rear_top.png').convert('RGB').resize((570,370)),(25,1090))
lines(d,(615,1110),['小图单独显示后件内部，盒内未放电池。','橙色为 3 厚竖肋；中央另有 8×4 局部连接面。','旧实体 123.814 cm³ → 新实体 45.637 cm³，减少约 63.14%。','后件：底面朝下、口朝上；弧托内侧局部悬伸需要支撑。'],22,gap=42)
im.save(ROOT/'03_top.png')
print('Three annotated review images saved.')
