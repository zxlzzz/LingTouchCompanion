from pathlib import Path
import json
from PIL import Image,ImageDraw,ImageFont
P=Path(__file__).resolve().parent;W=P/'views'
s=json.loads((P/'audit/solid_collision_audit.json').read_text())
h=json.loads((P/'audit/surface_clearance_audit.json').read_text())
ink='#253745'
def font(n):return ImageFont.load_default(size=n)
def lines(d,xy,items,size=24,gap=47):
 x,y=xy
 for line in items:d.text((x,y),line,font=font(size),fill=ink);y+=gap
def paste(im,name,box):
 src=Image.open(W/(name+'.png')).convert('RGB');src.thumbnail((box[2],box[3]));im.paste(src,(box[0]+(box[2]-src.width)//2,box[1]+(box[3]-src.height)//2))
def canvas(title,height=1350):
 im=Image.new('RGB',(1600,height),'white');d=ImageDraw.Draw(im)
 lines(d,(40,20),[title,'检查版｜灰：头模及BTTF原件；青：当前前件；紫：后脑件；蓝：25宽带子。'],30,55)
 return im,d
for index,name,title,notes in [
 (1,'front_raw','01 前视｜两端侧壁补齐，上端敞开',[
  f'整体95×35.4×29.7mm；实体{s["volume_cm3"]:.3f}cm³。',
  '盒子与前件、头模、带子不相交；前件保持原样。']),
 (2,'side_raw','02 侧视｜底部连接与盒底齐平',[
  '盒底、弧托、肋、中央薄连接、穿带板最低面统一到Z=25.5。',
  '带子悬空：左46.303mm／右46.308mm；镜腿不截。']),
 (3,'top_raw','03 俯视｜电池从上方放入',[
  '电池轴沿X；直通上口91×23.4，底至口沿深25.4。',
  '弧托宽40；与盒间大空当保留，只由薄舌和竖肋连接。'])]:
 im,d=canvas(title);paste(im,name,(40,150,1520,960));lines(d,(45,1140),notes,25,55)
 d.text((45,1280),'佩戴朝向预览；本次仍是检查模型，尚未定版。',font=font(22),fill=ink)
 im.save(P/(f'0{index}_'+['front','side','top'][index-1]+'.png'))
im,d=canvas('后脑件细节｜补侧壁，底部齐平',1550)
paste(im,'rear_empty_iso',(20,150,990,780))
lines(d,(1020,230),['两端侧壁2mm','仅上方敞开','接口名义孔12×6','接口实物位置没查',f'实体{s["volume_cm3"]:.3f}cm³','整体95×35.4×29.7'],24,67)
paste(im,'rear_bottom_iso',(20,925,740,545))
paste(im,'rear_open_end',(810,965,360,405))
lines(d,(1180,1030),['底边Z=25.5','穿带孔26×3','下边料0.7','强度没查'],24,66)
lines(d,(30,1478),['左下：底面与薄连接；右下：补齐的接口端侧壁。单位mm。'],24)
im.save(P/'Rear_FlatBase_Detail.png')
sheet=Image.new('RGB',(2400,2050),'#e9edef');d=ImageDraw.Draw(sheet)
for i,name in enumerate(['01_front.png','02_side.png','03_top.png']):
 src=Image.open(P/name);src.thumbnail((1180,990));x=10+(i%2)*1200;y=10+(i//2)*1020;sheet.paste(src,(x+(1180-src.width)//2,y))
lines(d,(1240,1100),['后脑件检查版','两端补侧壁，顶部敞开','连接与底面同高Z=25.5','95×35.4×29.7mm',f'实体{s["volume_cm3"]:.3f}cm³','前件和带子路径未动','穿带孔下边料0.7，待实测'],32,95)
sheet.save(P/'Review_Three_Views.png')
print('Three wearing views and detail views written.')
