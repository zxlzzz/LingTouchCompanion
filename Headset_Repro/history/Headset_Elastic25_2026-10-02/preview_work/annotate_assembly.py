from pathlib import Path
import json
from PIL import Image,ImageDraw,ImageFont
ROOT=Path(__file__).resolve().parents[1];W=ROOT/'preview_work'
F=None;ink='#263847';teal='#138798';purple='#8060a2';blue='#3169ae';red='#be302b';gray='#899298'
def font(n):return ImageFont.load_default(size=n)
def lines(d,xy,items,size=23,color=ink,gap=38):
 x,y=xy
 for item in items:d.text((x,y),item,font=font(size),fill=color);y+=gap
def canvas(title):
 im=Image.new('RGB',(1600,1320),'white');d=ImageDraw.Draw(im)
 d.text((42,24),title,font=font(37),fill=ink)
 d.text((42,80),'按本次尺寸实际建模；灰色头模保持原比例与试摆。当前连接存在碰撞，尚不能定版。单位 mm。',font=font(22),fill=ink)
 x=42
 for col,label in [(gray,'头模／原 BTTF'),(teal,'相机壳／32 高耳片'),(purple,'弧托＋盒子'),(blue,'候选带段（不可装）'),(red,'实际重叠／无效截短')]:
  d.rectangle((x,128,x+20,148),fill=col);d.text((x+27,124),label,font=font(21),fill=ink);x+=int(font(21).getlength(label))+52
 return im,d
im,d=canvas('01  前视｜前件保留，后脑改为弧托＋平盒')
im.paste(Image.open(W/'front_raw.png').convert('RGB').resize((1050,665)),(28,180))
lines(d,(1110,215),['前耳片高度 32','上沿 Z=55.2','底沿 Z=23.2','竖缝 26 × 3','松紧带宽 25','镜腿本轮截短 0'],24,gap=47)
lines(d,(1110,565),['后托高 47','Z=8.2 到 55.2','总宽 145.6','平盒外宽 121.6','两端各多伸 12'],24,gap=43)
im.paste(Image.open(W/'rear_iso.png').convert('RGB').resize((540,375)),(1015,835))
lines(d,(45,900),['曲托内表面到头模：整面范围已核在 0.307～1.693 内。','这是连续面的保守界限；整面真实极值：没查。','盒内腔 117.6 × 15.6 × 45；壁与底 2，顶开口。','电池露 2；凸点 0.8；一端接口豁口 11 × 35。','弧托名义壁厚 2.5；网格实际最薄 2.47431。'],23,gap=42)
lines(d,(45,1176),['相机壳及鼻道保持已通过版；32 高耳片和 26×3 槽已改。','后脑件只出预览；前件 3MF 等连接位置确定后再出。'],23,color=red,gap=40)
im.save(ROOT/'01_front.png')

im,d=canvas('02  侧视｜贴头弧托的端部与前耳片重叠')
im.paste(Image.open(W/'side_raw.png').convert('RGB'),(50,165))
lines(d,(45,1073),['红色：前件与后件实际重叠 1305.373 mm³；目前不能按两件装配。','两槽候选距离：左 4.115／右 4.070；线路穿托壁，不能算有效自由带。','纸面 40 需截左 35.901／右 35.936；槽将侵头 16.125／16.569，未应用。','后件最厚处（同一 X、Z 的前后外轮廓）：72.139；整体 Y 跨度：99.704。','连接需调整：将穿带端后移，主体弧托仍贴头；尚待确认。'],23,gap=39)
im.save(ROOT/'02_side.png')

im,d=canvas('03  俯视｜两件摆位、候选带段及无效截短位置')
im.paste(Image.open(W/'top_raw.png').convert('RGB').resize((1125,900)),(230,168))
def pixel(x,y):return (230+1125/2+x*1125/350,168+900/2-(y-97)*1125/350)
connection=json.loads((ROOT/'connection/elastic25_free_path_audit.json').read_text())
for side,row in connection['sides'].items():
 a=row['current_front_free_contact_xyz_mm'];b=row['rear_free_contact_xyz_mm'];p=pixel(a[0],a[1]);q=pixel(b[0],b[1]);d.line([p,q],fill=blue,width=5)
 k=row['geometric40_front_contact_xyz_mm'];kx,ky=pixel(k[0],k[1]);d.ellipse((kx-9,ky-9,kx+9,ky+9),outline=red,width=3)
 for step in range(0,32,2):
  t0=step/32;t1=(step+1)/32;d.line([(kx+(q[0]-kx)*t0,ky+(q[1]-ky)*t0),(kx+(q[0]-kx)*t1,ky+(q[1]-ky)*t1)],fill=red,width=2)
lines(d,(35,230),['图上方为后方','后盒与曲托间','空当已填实','连成一个件','总宽 145.6','高 47'],21,gap=42)
lines(d,(1380,400),['蓝：候选短带','实际穿后托壁','尚不能使用','红点：纸面40','的新前槽位置','实际侵入头模','未做截短'],20,color=red,gap=37)
lines(d,(45,1091),['不穿头的前槽截短极限：左 1.078／右 0.679，仍达不到 40～60。','当前未截腿；红虚线只显示纸面 40 的计算，不能当成可佩戴路线。','后盒底平面朝下、口朝上打印；托内侧局部悬伸要支撑，竖缝顶桥跨 3。','前件顶平面朝下；相机腔顶棚要支撑；M2×10。实际切片／插拔：没查。'],23,gap=42)
im.save(ROOT/'03_top.png')
print('Three annotated rear-review views saved.')
