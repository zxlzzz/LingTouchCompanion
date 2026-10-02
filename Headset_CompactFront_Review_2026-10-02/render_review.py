"""Render measured review meshes only; no shape retouching."""
from pathlib import Path
import math
import numpy as np
import bpy
from mathutils import Vector

P=Path(__file__).resolve().parent
G=P/'geometry'
OLD=P.parent/'Headset_Carbon6K_FlatBase_Review_2026-10-02/inputs'
W=P/'views';W.mkdir(exist_ok=True)
bpy.ops.wm.read_factory_settings(use_empty=True)
scene=bpy.context.scene
scene.render.engine='BLENDER_WORKBENCH'
scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG'
scene.world=bpy.data.worlds.new('white');scene.world.color=(1,1,1)
sh=scene.display.shading
sh.light='STUDIO';sh.color_type='OBJECT';sh.studiolight_rotate_z=.5
sh.show_shadows=True;sh.show_cavity=True;sh.cavity_type='BOTH'
sh.show_object_outline=True;sh.object_outline_color=(.2,.25,.28)
sh.background_type='WORLD'
scene.view_settings.view_transform='Standard';scene.view_settings.look='None'
objects={}

def mesh(name,path,color,section=None):
    a=np.load(path);v=a['v'];f=a['f']
    if section is not None:
        # The reference head is a display surface, not a manufactured solid.
        f=f[np.mean(v[f][:,:,0],axis=1)>=section]
    me=bpy.data.meshes.new(name);me.from_pydata(v.tolist(),[],f.tolist());me.update()
    ob=bpy.data.objects.new(name,me);scene.collection.objects.link(ob)
    ob.color=color;objects[name]=ob
    for poly in me.polygons:poly.use_smooth=True
    me.set_sharp_from_angle(angle=math.radians(5))
    return ob

colors={'original':(.64,.68,.70,1),'shell':(.07,.56,.65,1),
        'camera':(.94,.48,.10,1),'tabs':(.07,.56,.65,1),
        'head':(.80,.81,.80,.28),'rear':(.49,.33,.68,1),
        'straps':(.19,.41,.75,1)}
for name,file in [('original','original_modified'),('shell','new_shell'),
                  ('camera','camera'),('tabs','front_tabs')]:
    mesh(name,G/(file+'.npz'),colors[name])
mesh('head',OLD/'head_display.npz',colors['head'])
REAR=P.parent/'Headset_Carbon6K_FlatBase_Review_2026-10-02/geometry'
mesh('rear',REAR/'rear_unified_preview.npz',colors['rear'])
mesh('straps',REAR/'straps_preview.npz',colors['straps'])
data=bpy.data.cameras.new('ortho');cam=bpy.data.objects.new('ortho',data)
scene.collection.objects.link(cam);scene.camera=cam
data.type='ORTHO';data.clip_end=3000;data.clip_start=.01

def render(name,pos,target,scale,size,show):
    for n,ob in objects.items():ob.hide_render=n not in show
    cam.location=pos
    cam.rotation_euler=(Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler()
    data.ortho_scale=scale
    scene.render.resolution_x,scene.render.resolution_y=size
    scene.render.filepath=str(W/(name+'.png'))
    bpy.ops.render.render(write_still=True)

assembly={'original','shell','camera','tabs','head','rear','straps'}
front={'original','shell','camera','tabs'}
render('front_raw',(0,-700,53),(0,95,53),245,(1440,940),assembly)
render('side_raw',(700,92,48),(0,92,48),305,(1500,920),assembly)
render('top_raw',(0,93,700),(0,93,48),310,(1350,1150),assembly)
render('front_detail',(0,-700,32),(0,0,32),160,(1250,680),front)
render('front_iso',(180,70,140),(0,3,31),155,(1100,820),front)
# Head-side classification at representative points, supplementary to the
# exact positive distance certificate (same open-neck head reference).
from mathutils.bvhtree import BVHTree
h=np.load(P.parent/'Headset_Carbon6K_FlatBase_Review_2026-10-02/inputs/Medium_Trial_Registered.npz')
bvh=BVHTree.FromPolygons([Vector(q) for q in h['v']],h['f'].tolist(),all_triangles=True)
a=np.load(G/'camera.npz');points=np.vstack([a['v'],a['v'][a['f']].mean(1)])
classification=[]
for q in points:
 hit=bvh.ray_cast(Vector((q[0],-200,q[2])),Vector((0,1,0)),600)
 classification.append({'camera_xyz_mm':q.tolist(),'head_front_y_mm':None if hit[0] is None else hit[0].y,'anterior':True if hit[0] is None else bool(q[1]<hit[0].y)})
import json
(P/'audit/camera_head_side_samples.json').write_text(json.dumps(classification,indent=2),encoding='utf8')
print('Review views rendered.')
