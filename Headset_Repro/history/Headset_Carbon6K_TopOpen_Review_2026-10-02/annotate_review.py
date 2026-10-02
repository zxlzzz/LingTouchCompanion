from pathlib import Path
import json
from PIL import Image,ImageDraw,ImageFont
P=Path(__file__).resolve().parent;W=P/'views';g=json.loads((P/'geometry/geometry_values.json').read_text());a=json.loads((P/'audit/surface_clearance_audit.json').read_text());s=json.loads((P/'audit/solid_collision_audit.json').read_text())
ink='#253745';purple='#8060a2';blue='#3169ae'
def font(n):return ImageFont.load_default(size=n)
def lines(d,xy,items,size=23,gap=45):
 x,y=xy
 for t in items:d.text((x,y),t,font=font(size),fill=ink);y+=gap
def canvas(title,h=1490):
 im=Image.new('RGB',(1600,h),'white');d=ImageDraw.Draw(im);d.text((40,20),title,font=font(34),fill=ink)
 d.text((40,77),'后脑上开口检查版｜电池仍横放；最新前件、头模、弧托及穿带位置保留。单位mm。',font=font(22),fill=ink)
 x=40
 for col,label in [('#849097','BTTF原件'),('#128b9d','当前前件'),(purple,'后脑件'),(blue,'25宽带子'),('#c9a537','电池占位'),('#b5bbb8','原头模')]:
  d.rectangle((x,121,x+19,140),fill=col);d.text((x+27,116),label,font=font(21),fill=ink);x+=int(font(21).getlength(label))+53
 return im,d
im,d=canvas('01  前视｜后脑盒改成顶部敞开',1540)
im.paste(Image.open(W/'front_raw.png').convert('RGB').resize((1180,770)),(10,170))
lines(d,(1220,250),['总宽95','总深35.4','总高32',f'实体{s["volume_cm3"]:.3f}cm³','弧托宽40','中心Z=39.2'],23,gap=53)
im.paste(Image.open(W/'rear_empty_iso.png').convert('RGB').resize((750,585)),(20,930))
lines(d,(810,1020),['小图：空盒，可直接看到上端完整敞开。','两端有挡壁，电池从上方放入／向上取出。','口部91×23.4；底至口沿净深25.4。','外形高度保留；原2厚顶壁已去掉。','接口端保留18宽的接线豁口。','底部侧插钩取消，改为背壁U缝弹片。','弧托和穿带板的位置没有移动。'],23,gap=48)
im.save(P/'01_front.png')
im,d=canvas('02  侧视｜盒中心与带子中心仍对齐')
im.paste(Image.open(W/'side_raw.png').convert('RGB'),(50,165))
lo,hi=a['rear_inner_surface']['continuous_surface_distance_bound_mm']
lines(d,(45,1130),['带子悬空段：左46.303／右46.308；镜腿与穿带位置不改。',f'弧托整面距头模的保守范围{lo:.3f}～{hi:.3f}；最近实体距头0.996。','后脑件与当前前件、头模、带子不相交。','电池向上移27.401后完全退出；除弹片钩外，连续取放路径无碰撞。','打印改为底部朝下、顶部开口朝上；盒底及弧托外部需要支撑。'],23,gap=49)
im.save(P/'02_side.png')
im,d=canvas('03  俯视｜顶板去掉，电池横向放入上开口',1600)
im.paste(Image.open(W/'top_raw.png').convert('RGB').resize((1215,1035)),(210,170))
im.paste(Image.open(W/'rear_top.png').convert('RGB').resize((600,408)),(20,1180))
lines(d,(660,1270),['小图是空盒俯视，上方没有顶板。','盒子95×27.4×27.4；后脑整体95×35.4×32。','背壁弹片凸钩0.8；实物弹性与插头细部没查。','最新前件仅作佩戴参照，本次没有修改。','这是佩戴朝向的检查模型，不是打印定版。'],22,gap=50)
im.save(P/'03_top.png')
# Clear change-detail image to accompany the wearing model link.
im=Image.new('RGB',(1500,1200),'white');d=ImageDraw.Draw(im)
d.text((40,20),'后脑盒：顶部敞开，电池从上方放入',font=font(34),fill=ink)
im.paste(Image.open(W/'rear_empty_iso.png').convert('RGB').resize((1250,975)),(125,85))
lines(d,(45,1090),[f'95×35.4×32mm，实体{s["volume_cm3"]:.3f}cm³；接口端仅留接线豁口，电池不从侧端装入。','检查模型保持佩戴方向；前件、头模、弧托与穿带位置不动。'],23,gap=45)
im.save(P/'Rear_TopOpen_Detail.png')
sheet=Image.new('RGB',(2400,2250),'#e9edef');d=ImageDraw.Draw(sheet)
for i,name in enumerate(['01_front.png','02_side.png','03_top.png']):
 im=Image.open(P/name).convert('RGB');im.thumbnail((1180,1080));x=10+(i%2)*1200;y=10+(i//2)*1110;sheet.paste(im,(x+(1180-im.width)//2,y))
lines(d,(1240,1240),['后脑改为上开口','电池沿X横放，沿Z取放','整体95×35.4×32',f'实体{s["volume_cm3"]:.3f}cm³','穿带位置不动，带长46.3','前件、头模及弧托保留','这份是检查版'],34,gap=100)
sheet.save(P/'Review_Three_Views.png')
print('Three assembly views, detail and montage saved.')
