"""Draw true plane sections from Manifold contours, without distant walls."""
from pathlib import Path
import json
import numpy as np
import manifold3d as md
import trimesh
from PIL import Image,ImageDraw,ImageFont

P=Path(__file__).resolve().parent;G=P/'geometry';W=P/'views'
FONT=None
def font(n):return ImageFont.load_default(size=n)
T=[[0,-1,0,0],[0,0,1,0],[-1,0,0,0]]
def contours(path,x):
    a=np.load(path)
    m=md.Manifold(md.Mesh64(vert_properties=np.ascontiguousarray(a['v'],dtype=np.float64),
                           tri_verts=np.ascontiguousarray(a['f'],dtype=np.uint64)))
    if m.status()!=md.Error.NoError:
        assert 'headform' in str(path),(path,m.status())
        segments=trimesh.intersections.mesh_plane(
            trimesh.Trimesh(a['v'],a['f'],process=False),
            plane_origin=[x,0,0],plane_normal=[1,0,0])
        return [np.column_stack([-p[:,1],p[:,2]]) for p in segments]
    return [np.asarray(p) for p in m.transform(T).slice(-x).to_polygons()]
def area(p):return .5*np.sum(p[:,0]*np.roll(p[:,1],-1)-p[:,1]*np.roll(p[:,0],-1))

scale=15;ox=695;oy=1060
def pix(p):return (ox+scale*p[0],oy-scale*p[1])
def layer(im,polys,color):
    mask=Image.new('L',im.size,0);d=ImageDraw.Draw(mask)
    for p in sorted(polys,key=lambda a:abs(area(a)),reverse=True):
        if len(p)<3:continue
        d.polygon([pix(q) for q in p],fill=255 if area(p)>0 else 0)
    colored=Image.new('RGBA',im.size,color)
    if color[3]<255:mask=mask.point(lambda v:int(v*color[3]/255))
    im.paste(colored,(0,0),mask)
    d=ImageDraw.Draw(im)
    for p in polys:
        points=[pix(q) for q in p]
        d.line(points+[points[0]],fill=color[:3],width=2)

head=P.parent/'Headset_FullCase_30mm_Preview_2026-10-02/headform/Medium_Trial_Registered.npz'
record={}
for x in [0,30]:
    im=Image.new('RGB',(1600,1150),'white');d=ImageDraw.Draw(im)
    d.text((45,25),f'真实平面剖切：X = {x} mm',font=font(28),fill='#253745')
    sets={name:contours(path,x) for name,path in [
        ('head',head),('original',G/'original_modified.npz'),
        ('shell',G/'new_shell.npz'),('camera',G/'camera.npz')]}
    # Exact section contours of the head retain the established pose.
    layer(im,sets['head'],(182,188,185,70))
    layer(im,sets['original'],(120,133,139,255))
    layer(im,sets['shell'],(16,139,157,255))
    layer(im,sets['camera'],(228,147,51,255))
    d=ImageDraw.Draw(im)
    for z,color in [(0,'#91999e'),(55.2,'#b5bcc0'),(60,'#c1413b')]:
        yy=pix([0,z])[1]
        for xx in range(85,1510,24):d.line((xx,yy,xx+13,yy),fill=color,width=2)
        d.text((90,yy-29),f'Z={z:g}',font=font(19),fill=color)
    yy=pix([0,0])[1]
    d.line((pix([0,0]),pix([0,66])),fill='#bac1c5',width=2)
    d.text((ox+8,oy+15),'Y=0',font=font(20),fill='#60707b')
    d.text((1330,oy+15),'前方（-Y）→',font=font(21),fill='#253745')
    d.text((360,oy+15),'← 贴脸侧（+Y）',font=font(21),fill='#253745')
    im.save(W/f'section{x}_true.png')
    record[str(x)]={n:[a.tolist() for a in polys] for n,polys in sets.items()}
(W/'true_section_contours.json').write_text(json.dumps(record),encoding='utf8')
print('Two true sections drawn from exact CAD contours.')
