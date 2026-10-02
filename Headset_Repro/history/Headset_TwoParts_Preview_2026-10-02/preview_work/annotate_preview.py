from pathlib import Path
import json, math
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.patches import Polygon
ROOT=Path(__file__).resolve().parents[1];W=ROOT/'preview_work'
F=None
def font(n):return ImageFont.load_default(size=n)
ink='#263747';gray='#7b8796';teal='#16899a';gold='#c8791f';red='#bc3838';purple='#8060a1'
def canvas(title,subtitle):
 im=Image.new('RGB',(1600,1120),'white');d=ImageDraw.Draw(im)
 d.text((45,24),title,font=font(39),fill=ink)
 d.text((45,82),subtitle,font=font(24),fill=ink)
 cols=[(gray,'BTTF Normal 原网格'),(teal,'相机座／前耳片'),(gold,'相机尺寸占位'),(red,'必须填实区：与 Y<=0 冲突'),(purple,'后脑口袋')]
 x=45
 for col,t in cols:
  d.rectangle((x,133,x+20,153),fill=col);d.text((x+29,129),t,font=font(21),fill=ink);x+=int(font(21).getlength(t))+57
 return im,d
def block(d,xy,lines,size=24,color=ink,gap=36):
 x,y=xy
 for a in lines:d.text((x,y),a,font=font(size),fill=color);y+=gap
def line(d,a,b,label):
 d.line((a,b),fill=ink,width=2)
 for p in [a,b]:d.line((p[0],p[1]-7,p[0],p[1]+7),fill=ink,width=2)
 d.text(((a[0]+b[0])/2-font(23).getlength(label)/2,a[1]+8),label,font=font(23),fill=ink)
im,d=canvas('01  前视｜原网格 + 相机座','尺寸单位 mm。相机按指定位置保持不抬；红色为冲突诊断，尚未生成最终一体件。')
im.paste(Image.open(W/'front_raw.png').convert('RGB'),(50,165))
block(d,(52,785),['相机宽 89.94；相机座外宽 94.54（X=±47.27）','内腔截面 90.54 × 30.80；左右／顶间隙 0.30，底间隙 0.50','相机前脸整块外露；无镜片、无 USB 预留、无装饰孔'],23)
im.paste(Image.open(W/'pocket_iso.png').convert('RGB').resize((575,296)),(970,784))
block(d,(52,937),['后脑口袋：外包络 121.60 × 19.60 × 47.00（不含耳片）','两个后耳片均为暂定高 22、厚 2，向两端各伸出 12；槽 16 高 × 3 宽','前件原轮廓与贴脸面原样显示。是否能连成一个打印件：Y 限制未通过。'],23,gap=37)
im.save(ROOT/'01_front.png')
im,d=canvas('02  侧视｜位置与高度边界','X 方向观察。后脑口袋 Y=190 为带子连接示意位置；尚未按可佩戴头模固定前后距离。')
im.paste(Image.open(W/'side_raw.png').convert('RGB'),(50,167))
block(d,(60,706),['相机下倾 20°；四条棱按给定位置计算，误差仅为 0.01 的取整','相机前上棱 Y=-34.55292；前基准到最前点 34.55292 <= 35','相机座范围：Y=-28.26413…+1.93444，Z=16.12047…55.20000','新增前耳片：Z=33.20…55.20；终点 Y=159.07033（原端 +12）'],24)
block(d,(60,892),['口袋内深 45，47 高的充电宝实际露出 2.00（图中浅紫色）','接口侧豁口：11 宽 × 35 向下；开口底到内底剩 10','严格禁止新增到 Y>0：相机背板、填实连接区和指定后伸耳片无法同时满足。'],24,color=red,gap=39)
im.save(ROOT/'02_side.png')
im,d=canvas('03  俯视｜两件与穿带位置','图的下方是前方（Y 为负）；上方是后脑。15 宽带子为另加软带，不是打印件。')
im.paste(Image.open(W/'top_raw.png').convert('RGB').resize((756,840)),(414,178))
block(d,(45,216),['后脑口袋','内宽 117.60','内前后 15.60','两侧间隙各 0.30','上敞开，无盖','单点内凸 0.40','喉口仍有 0.20 余量','防滑效果：没查'],24,gap=43)
block(d,(1190,394),['前耳片','每端后伸 12','左厚 3.25905','右厚 3.41562','高 22','槽 16 × 3','（16 沿 Z）'],24,gap=42)
block(d,(45,720),['M2 底孔 Ø1.70','X=0；轴向位置 7.50','轴线垂直相机顶面','孔口到相机 6.35779','按轴向长度计：M2×8'],23,gap=40)
block(d,(1075,855),['灰色弧面保持原状。','红色连接区须进入 Y>0。','原贴脸面无需改变，','但这不等于满足 Y<=0。'],23,color=red,gap=40)
im.save(ROOT/'03_top.png')

plt.rcParams['font.family']='Microsoft JhengHei';plt.rcParams['axes.unicode_minus']=False
c,s=math.cos(math.radians(20)),math.sin(math.radians(20))
p=np.array([-.8,23.6]);u=np.array([-s,c]);n=np.array([-c,-s])
pt=lambda q,t:p+u*q+n*t
fig,ax=plt.subplots(figsize=(12.4,7.4),dpi=155);fig.patch.set_facecolor('white')
outer=np.array([pt(-2.5,-2),pt(-2.5,15),pt(32.3,15),pt(32.3,-2)])
ax.add_patch(Polygon(outer,fc=teal,ec=teal,alpha=.43,lw=1.8))
roof=np.array([pt(32.3,-2),pt(32.3,15),[-28.26412599,55.2],[0,55.2]])
ax.add_patch(Polygon(roof,fc=teal,ec=teal,alpha=.43))
inner=np.array([pt(-.5,0),pt(-.5,15.01),pt(30.3,15.01),pt(30.3,0)])
ax.add_patch(Polygon(inner,fc='white',ec=teal,lw=1))
cam=np.array([pt(0,0),pt(0,25),pt(30,25),pt(30,0)])
ax.add_patch(Polygon(cam,fc=gold,ec=gold,alpha=.40,lw=2))
def section(meshfile,axis=0,value=0):
 a=np.load(meshfile);v=a['v'];f=a['f'];tri=v[f]
 tri=tri[(tri[:,:,axis].min(axis=1)<value)&(tri[:,:,axis].max(axis=1)>value)]
 lines=[]
 for t in tri:
  points=[]
  for i,j in [(0,1),(1,2),(2,0)]:
   a,b=t[i],t[j]
   if (a[axis]-value)*(b[axis]-value)<0:
    q=a+(b-a)*(value-a[axis])/(b[axis]-a[axis]);points.append(q[[1,2]])
  if len(points)==2:lines.append(points)
 return np.array(lines)
orig=section(W/'original.npz');ax.add_collection(LineCollection(orig,colors=gray,linewidths=2.8,label='原网格剖面'))
head=json.loads((ROOT/'headform/head_registration_new.json').read_text())
nose=np.load(ROOT/'headform/nose_center_section.npz')['xyz']
if nose.ndim==3:
 ax.add_collection(LineCollection(nose[:,:,[1,2]],colors='#b4b7bc',linewidths=2,label='真实头模鼻部'))
else:ax.plot(nose[:,1],nose[:,2],color='#a9acb2',lw=2,label='真实头模鼻部')
hp=np.array(head['nominal_nose_point_mm'])[1:3];sp=np.array(head['nominal_socket_point_mm'])[1:3]
ax.plot([hp[0],sp[0]],[hp[1],sp[1]],color=red,lw=3)
ax.scatter([hp[0],sp[0]],[hp[1],sp[1]],color=red,s=30,zorder=12)
ax.annotate('头模试摆最小距离 1.03525\n见证点 X=-0.34361，投影至本剖面',xy=sp,xytext=(8,13),fontsize=10,color=red,
            arrowprops={'arrowstyle':'-','color':red})
entry=np.array([-20.2827927,55.2]);contact=pt(30,7.5)
ax.plot([entry[0],contact[0]],[entry[1],contact[1]],color='#344958',lw=2,ls='--')
ax.annotate('Ø1.7 底孔\n孔口到相机顶面 6.35779',xy=entry,xytext=(-38,60),fontsize=10,
            arrowprops={'arrowstyle':'-','color':'#344958'})
for name,q,t,off in [('后下',0,0,(7,-2)),('前下',0,25,(-13,-6)),('前上',30,25,(-12,4)),('后上',30,0,(4,6))]:
 v=pt(q,t);at=np.array([10.,49.]) if name=='后上' else v+off
 ax.annotate(f'{name} ({v[0]:.2f}, {v[1]:.2f})',xy=v,xytext=at,fontsize=9,color=gold,
                       arrowprops={'arrowstyle':'-','color':gold})
ax.axvline(0,color=red,lw=1,ls='--');ax.text(.8,58,'Y=0',color=red,fontsize=10)
ax.axhline(55.2,color='#647585',lw=.8,ls=':');ax.text(12,55.8,'Z=55.2',fontsize=10)
ax.annotate('背板外后下角 Y=+1.93444\n不能被 Y=0 裁掉：腔底背板仅剩 0.66936',xy=pt(-2.5,-2),xytext=(8,34),
             color=red,fontsize=10,arrowprops={'arrowstyle':'-','color':red})
ax.annotate('',xy=pt(-1.6,0),xytext=pt(-1.6,15),arrowprops={'arrowstyle':'<->','color':teal})
ax.text(-16.7,18.7,'筒深 15；前露 10',fontsize=10,color=teal)
ax.set_xlim(-50,39);ax.set_ylim(7,67);ax.set_aspect('equal');ax.set_xlabel('Y：前方为负（mm）');ax.set_ylabel('Z（mm）')
ax.grid(alpha=.13);fig.tight_layout();fig.savefig(W/'section_raw.png');plt.close(fig)
im,d=canvas('04  正中剖面｜鼻梁与相机座','灰色是 BTTF 原网格剖面／真实头模鼻部；头模未缩放。鼻梁数字属于试摆，佩戴未通过。')
sec=Image.open(W/'section_raw.png').convert('RGB');sec.thumbnail((1530,845));im.paste(sec,((1600-sec.width)//2,175))
block(d,(50,1004),['允许上抬最多 0.56389 → 试摆净空 1.37259；达到 3.00000 需抬 3.22650。','届时相机座顶角为 Z=57.86261，超出上沿 2.66261。原镜腿与头模还相交，不能报告已可佩戴。'],23,color=red,gap=37)
im.save(ROOT/'04_center_section.png')
print('Annotated four preview images.')
