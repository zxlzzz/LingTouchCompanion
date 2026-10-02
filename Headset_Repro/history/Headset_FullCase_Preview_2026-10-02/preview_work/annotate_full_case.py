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
FONT=None
def font(s):return ImageFont.load_default(size=s)
ink='#253747';gray='#7e8a98';teal='#16899a';gold='#c8791f';red='#b93535';purple='#8060a1'
def canvas(title,sub):
 im=Image.new('RGB',(1600,1120),'white');d=ImageDraw.Draw(im)
 d.text((45,24),title,font=font(39),fill=ink);d.text((45,83),sub,font=font(23),fill=ink)
 x=45
 for col,t in [(gray,'BTTF 原网格'),(teal,'新增外壳／前耳片'),(gold,'相机（仅前脸外露）'),(purple,'后脑口袋'),(red,'原轮廓或不通过位置')]:
  d.rectangle((x,133,x+20,153),fill=col);d.text((x+28,129),t,font=font(21),fill=ink)
  x+=int(font(21).getlength(t))+58
 return im,d
def block(d,xy,lines,size=23,color=ink,gap=37):
 x,y=xy
 for line in lines:d.text((x,y),line,font=font(size),fill=color);y+=gap

im,d=canvas('01  前视｜完整包覆外壳','相机位置保持不变；只显示前脸。原件贴脸面仅新增指定的 Ø4 顶出孔。尺寸单位 mm。')
im.paste(Image.open(W/'front_raw.png').convert('RGB'),(50,166))
# Overlay measured original nose silhouette, sampled from original triangle cuts.
ref=np.load(W/'original_reference.npz');tri=ref['v'][ref['f']]
def zlow(x):
 t=tri[(tri[:,:,0].min(axis=1)<=x)&(tri[:,:,0].max(axis=1)>=x)];z=[]
 for i,j in [(0,1),(1,2),(2,0)]:
  a,b=t[:,i],t[:,j];dd=b[:,0]-a[:,0];ok=(abs(dd)>1e-12)&((a[:,0]-x)*(b[:,0]-x)<=0)
  z.extend((a[ok,2]+(b[ok,2]-a[ok,2])*(x-a[ok,0])/dd[ok]).tolist())
 return min(z)
outline=[]
for x in np.linspace(-12,12,121):
 z=zlow(x);outline.append((800+x*1500/166,166+330-(z-27.6)*1500/166))
for i in range(0,len(outline)-1,4):d.line(outline[i:min(i+3,len(outline))],fill=red,width=3)
block(d,(50,796),['中央外壳宽 94.60（X=±47.30）；相机腔 90.54 × 30.80 × 25','左右、顶各留 0.30；底留 0.50；鼻道顶壁厚 2.00','红虚线：原鼻缺口投影；新底壁最低 Z=12.70026，原中心为 20.60790'],23)
block(d,(50,937),['整体外宽保持 142.3133，新增外壳未越过左右外边。','鼻缺口投影正中多出 7.90764；原鼻缺口网格本身未改。','后袋：凸点改为 0.80；喉口 14.80，对电池需退让至少 0.20。'],23,color=red)
im.paste(Image.open(W/'pocket_iso.png').convert('RGB').resize((510,267)),(1038,837))
im.save(ROOT/'01_front.png')

im,d=canvas('02  侧视｜相机在壳内','后袋 Y=190 仅作带子连接示意；前件与原件实际布尔并集已经连成一个实体。')
im.paste(Image.open(W/'side_raw.png').convert('RGB'),(50,168))
block(d,(50,707),['外壳正面：低于 Z=43.24028 为相机前脸斜面；上方为 Y=-34.55292 竖直面','顶面 Z=55.20；底面 Z=0（正中鼻道除外）；两翼在 |X|=65 接回原件，此接点为暂定','最前距离 34.55292 <= 36，余 1.44708；相机未前移、未上抬','前框正中含原壁的总深度约 37.95；整前件含镜腿耳片长 193.62325'],23,gap=39)
block(d,(50,887),['相机前脸名义缩进 0.00；全部机身都在外包络以内。','前上沿沿相机顶面法向有约 0.10919 长的封边不足，已记录，未另加凸起。','新鼻道 26 宽：新增 Y<0 实体到鼻面最小 1.25782，未达 2。'],23,color=red,gap=39)
im.save(ROOT/'02_side.png')

im,d=canvas('03  俯视｜顶孔、原镜腿与后袋','图下方为前方（Y 为负）。两条镜腿、末端耳片、后袋尺寸沿用上一版。')
im.paste(Image.open(W/'top_raw.png').convert('RGB').resize((756,840)),(414,178))
block(d,(45,212),['后袋内腔','117.60 × 15.60 × 45','壁与底均 2','电池每边余 0.30','实际露出 2.00','接口豁口 11 × 35','凸点向内 0.80','插拔／防滑：没查'],23,gap=42)
block(d,(1190,393),['前耳片保持','后伸 12；高 22','左厚 3.25905','右厚 3.41562','竖缝 16 × 3','槽上下余 3'],23,gap=42)
block(d,(45,738),['顶面 M2 底孔 Ø1.70','X=0；光轴位置 12.50','轴线垂直相机顶面','孔口到相机 8.17765','所需螺丝：M2×10'],23,gap=41)
block(d,(1080,838),['贴脸面顶出孔 Ø4','背板中心沿光轴穿过原件','后孔中心：','(0, 3.39402, 41.08917)','除此之外保护原贴脸面'],21,gap=40)
im.save(ROOT/'03_top.png')

plt.rcParams['font.family']='Microsoft JhengHei';plt.rcParams['axes.unicode_minus']=False
def section(meshfile):
 a=np.load(meshfile);t=a['v'][a['f']];t=t[(t[:,:,0].min(axis=1)<=1e-10)&(t[:,:,0].max(axis=1)>=-1e-10)]
 out=[]
 for tri in t:
  pts=[]
  for i,j in [(0,1),(1,2),(2,0)]:
   a,b=tri[i],tri[j]
   if abs(a[0])<1e-10:pts.append(a[[1,2]])
   if a[0]*b[0]<0:pts.append((a+(b-a)*(-a[0])/(b[0]-a[0]))[[1,2]])
  pts=np.unique(np.round(pts,9),axis=0) if pts else []
  if len(pts)==2:out.append(pts)
 return np.array(out)
def fill_loops(ax,segments,color):
 # Join actual section endpoints; fill bounded material loops.
 edges={};positions={}
 for a,b in segments:
  ka=tuple(np.round(a,6));kb=tuple(np.round(b,6))
  if ka==kb:continue
  positions[ka]=a;positions[kb]=b;edges.setdefault(ka,set()).add(kb);edges.setdefault(kb,set()).add(ka)
 seen=set()
 for start in list(edges):
  for nxt in list(edges[start]):
   key=frozenset([start,nxt])
   if key in seen:continue
   loop=[start];prev,current=start,nxt;seen.add(key)
   for _ in range(len(edges)+2):
    loop.append(current)
    if current==start:break
    choices=[x for x in edges[current] if x!=prev and frozenset([current,x]) not in seen]
    if not choices:break
    new=choices[0];seen.add(frozenset([current,new]));prev,current=current,new
   if loop[-1]==start and len(loop)>3:ax.add_patch(Polygon([positions[k] for k in loop],fc=color,ec='none',alpha=.25))
c,s=math.cos(math.radians(20)),math.sin(math.radians(20));p=np.array([-.8,23.6]);u=np.array([-s,c]);n=np.array([-c,-s])
pt=lambda q,t:p+u*q+n*t
fig=plt.figure(figsize=(13,7.0),dpi=155);ax=fig.add_axes([.06,.12,.62,.82])
actual=section(W/'case_material.npz');fill_loops(ax,actual,teal)
ax.add_collection(LineCollection(actual,colors=teal,linewidths=1.5))
ori=section(W/'original_modified.npz');ax.add_collection(LineCollection(ori,colors=gray,linewidths=2.4))
cam=np.array([pt(0,0),pt(0,25),pt(30,25),pt(30,0)])
ax.add_patch(Polygon(cam,fc=gold,ec=gold,alpha=.4,lw=1.8))
nose=np.load(ROOT/'headform/nose_center_section.npz')['xyz']
if nose.ndim==3:ax.add_collection(LineCollection(nose[:,:,[1,2]],colors='#b2b5bb',linewidths=2))
else:ax.plot(nose[:,1],nose[:,2],color='#b2b5bb',lw=2)
entry=np.array([-25.60368156,55.2]);contact=pt(30,12.5)
ax.plot([entry[0],contact[0]],[entry[1],contact[1]],color=ink,ls='--',lw=1.5)
ax.annotate('M2 Ø1.7；光轴位置 12.5\n孔口至相机 8.17765',xy=entry,xytext=(-39,62),fontsize=9,color=ink,
            arrowprops={'arrowstyle':'-','color':ink})
rc=pt(15,0);back=np.array([3.39401996,41.08916502])
ax.plot([rc[0],back[0]],[rc[1],back[1]],color=ink,ls='--',lw=1.3)
ax.annotate('Ø4 顶出孔\n轴线长 9.92274',xy=back,xytext=(9,42),fontsize=9,color=ink,
            arrowprops={'arrowstyle':'-','color':ink})
for name,q,t,at in [('后下',0,0,(4,27)),('前下',0,25,(-40,10)),('前上',30,25,(-43,47)),('后上',30,0,(6,50))]:
 point=pt(q,t);ax.annotate(f'{name} ({point[0]:.2f}, {point[1]:.2f})',xy=point,xytext=at,fontsize=8.5,color=gold,
                          arrowprops={'arrowstyle':'-','color':gold})
ax.axvline(0,color=red,ls=':',lw=1);ax.axhline(55.2,color=gray,ls=':',lw=1)
ax.text(12,56,'Z=55.2',fontsize=9);ax.text(.7,60,'Y=0',fontsize=9,color=red)
ax.annotate('中央鼻道顶壁 2\n前缘 Z=12.70026',xy=pt(-2.5,25),xytext=(-37,2),fontsize=9,color=teal,
            arrowprops={'arrowstyle':'-','color':teal})
ax.set_xlim(-46,20);ax.set_ylim(-2,67);ax.set_aspect('equal');ax.set_xlabel('Y（前方为负，mm）');ax.set_ylabel('Z（mm）');ax.grid(alpha=.12)
# Minimum is not on X=0: provide a separate XZ projection of exact witnesses.
mn=json.loads((ROOT/'headform/actual_case_nose_distance.json').read_text())
ax2=fig.add_axes([.72,.39,.25,.48]);hp=np.array([-11.904894072,.368083199,-.497349046]);cp=np.array([-13.,-1e-6,0.])
ax2.plot([cp[0],cp[0]],[0,4],color=teal,lw=3);ax2.plot([-16,-13],[0,0],color=teal,lw=3)
ax2.scatter(hp[0],hp[2],color=gray,s=40);ax2.scatter(cp[0],cp[2],color=red,s=40)
ax2.plot([hp[0],cp[0]],[hp[2],cp[2]],color=red,lw=1.5)
ax2.text(-15.8,3.0,'鼻道侧壁下后角\nX、Z 投影（非正中）',fontsize=9)
ax2.text(-15.8,1.35,'真实三维距离\n1.257815 < 2',fontsize=11,color=red)
ax2.set_xlim(-16,-10);ax2.set_ylim(-2,4.2);ax2.set_aspect('equal');ax2.set_xlabel('X（mm）');ax2.set_ylabel('Z（mm）');ax2.grid(alpha=.15)
fig.text(.72,.21,'只取原件之外新增材料，Y <= -0.000001。\n灰点是原头模鼻面，未缩放／未移动头模。\n正中鼻道剖面不能代表最小鼻距。',fontsize=9,color=ink)
fig.savefig(W/'section_raw.png');plt.close(fig)
im,d=canvas('04  正中剖面｜整台相机包在壳内','蓝线为实际新增外壳剖面，灰线为原件与原比例头模。虚线表示两个孔的轴线。')
sec=Image.open(W/'section_raw.png').convert('RGB');sec.thumbnail((1530,835));im.paste(sec,((1600-sec.width)//2,173))
block(d,(50,1004),['鼻距检查仅包含新增且 Y<0 的材料：连续最小值 1.25782，未达 2。','保持本次 26 宽鼻道未修改；扩大通道仅作另外的解析试算，未应用。'],23,color=red,gap=37)
im.save(ROOT/'04_center_section.png')
print('Four annotated full-case previews saved.')
