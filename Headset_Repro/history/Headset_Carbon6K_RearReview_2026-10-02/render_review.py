"""Render unchanged front/head and the actual new rear candidate."""
from pathlib import Path
import math
import numpy as np
import bpy
from mathutils import Vector

P=Path(__file__).resolve().parent;G=P/'geometry';W=P/'views';W.mkdir(exist_ok=True)
F=P.parent/'Headset_ThinShell_Review_2026-10-02/geometry'
OLD=P.parent/'Headset_FinalFront_RearPreview_2026-10-02'
bpy.ops.wm.read_factory_settings(use_empty=True)
scene=bpy.context.scene;scene.render.engine='BLENDER_WORKBENCH'
scene.render.resolution_percentage=100;scene.render.image_settings.file_format='PNG'
scene.world=bpy.data.worlds.new('white');scene.world.color=(1,1,1)
sh=scene.display.shading;sh.light='STUDIO';sh.color_type='OBJECT'
sh.studiolight_rotate_z=.5;sh.show_shadows=True;sh.show_cavity=True;sh.cavity_type='BOTH'
sh.show_object_outline=True;sh.object_outline_color=(.2,.25,.28);sh.background_type='WORLD'
scene.view_settings.view_transform='Standard';scene.view_settings.look='None'
objects={}
def mesh(name,path,color):
    a=np.load(path);me=bpy.data.meshes.new(name)
    me.from_pydata(a['v'].tolist(),[],a['f'].tolist());me.update()
    ob=bpy.data.objects.new(name,me);scene.collection.objects.link(ob);ob.color=color
    objects[name]=ob
    for poly in me.polygons:poly.use_smooth=True
    me.set_sharp_from_angle(angle=math.radians(5))
    return ob
for name,file,color in [('BTTF','original_modified',(.64,.68,.70,1)),
                        ('front_shell','new_shell',(.07,.56,.65,1)),
                        ('front_tabs','front_tabs',(.07,.56,.65,1)),
                        ('camera','camera',(.94,.48,.10,1))]:
    mesh(name,F/(file+'.npz'),color)
mesh('head',OLD/'preview_work/head_display.npz',(.80,.81,.80,.28))
mesh('rear',G/'rear_unified_preview.npz',(.49,.33,.68,1))
mesh('battery',G/'battery_preview.npz',(.92,.72,.23,1))
mesh('straps',G/'straps_preview.npz',(.19,.41,.75,1))
data=bpy.data.cameras.new('ortho');cam=bpy.data.objects.new('ortho',data)
scene.collection.objects.link(cam);scene.camera=cam
data.type='ORTHO';data.clip_end=3000;data.clip_start=.01
def render(name,pos,target,scale,size,show):
    for n,ob in objects.items():ob.hide_render=n not in show
    cam.location=pos
    cam.rotation_euler=(Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler()
    data.ortho_scale=scale
    scene.render.resolution_x,scene.render.resolution_y=size
    scene.render.filepath=str(W/(name+'.png'));bpy.ops.render.render(write_still=True)
assembly=set(objects)
render('front_raw',(0,-700,53),(0,95,53),245,(1440,940),assembly)
render('side_raw',(700,94,48),(0,94,48),310,(1500,920),assembly)
render('top_raw',(0,96,700),(0,96,48),320,(1350,1150),assembly)
render('rear_iso',(210,320,170),(0,210,39.2),125,(1000,780),{'rear','battery'})
render('rear_top',(0,213,700),(0,213,39.2),120,(1000,680),{'rear'})
render('rear_open_end',(700,216,39.2),(0,216,39.2),55,(650,680),{'rear','battery'})
print('Three assembly views and rear inspection insets rendered.')
