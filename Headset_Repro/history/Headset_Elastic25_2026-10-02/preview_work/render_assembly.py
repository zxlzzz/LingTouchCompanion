"""Render the rear-piece review with the unchanged registered anatomical head."""
from pathlib import Path
import numpy as np
import bpy
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1];W=ROOT/'preview_work'
bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene
scene.render.engine='BLENDER_WORKBENCH';scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.world=bpy.data.worlds.new('white');scene.world.color=(1,1,1)
sh=scene.display.shading;sh.light='STUDIO';sh.color_type='OBJECT';sh.studiolight_rotate_z=.5
sh.show_shadows=True;sh.show_cavity=True;sh.cavity_type='BOTH';sh.show_object_outline=True
sh.object_outline_color=(.2,.25,.28);sh.background_type='WORLD'
scene.view_settings.view_transform='Standard';scene.view_settings.look='None'
objects={}
def mesh(name,path,color):
 a=np.load(path);me=bpy.data.meshes.new(name);me.from_pydata(a['v'].tolist(),[],a['f'].tolist());me.update()
 ob=bpy.data.objects.new(name,me);scene.collection.objects.link(ob);ob.color=color;objects[name]=ob
 for poly in me.polygons:poly.use_smooth=True
 me.set_sharp_from_angle(angle=.0872664626)
 return ob
mesh('BTTF',ROOT/'front_work/original_modified.npz',(.62,.66,.69,1))
mesh('case',ROOT/'front_work/case_material.npz',(.1,.55,.63,1))
mesh('tabs',ROOT/'front_work/front_tabs.npz',(.1,.55,.63,1))
mesh('camera',ROOT/'front_work/camera.npz',(.9,.49,.12,1))
mesh('head',W/'head_display.npz',(.83,.83,.81,.28))
mesh('rear',ROOT/'rear_work/rear_unified_preview.npz',(.49,.33,.68,1))
mesh('straps',ROOT/'connection/straps_preview.npz',(.2,.41,.75,1))
mesh('battery',ROOT/'rear_work/battery_preview.npz',(.83,.77,.91,1))
overlap=mesh('overlap',ROOT/'connection/front_vs_rear_assembled_intersection.npz',(.90,.13,.12,1));overlap.show_in_front=True
objects['straps'].show_in_front=True
data=bpy.data.cameras.new('ortho');cam=bpy.data.objects.new('ortho',data);scene.collection.objects.link(cam);scene.camera=cam
data.type='ORTHO';data.clip_end=3000;data.clip_start=.01
def render(name,pos,target,scale,size,show):
 for n,ob in objects.items():ob.hide_render=n not in show
 cam.location=pos;cam.rotation_euler=(Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler()
 data.ortho_scale=scale;scene.render.resolution_x,scene.render.resolution_y=size
 scene.render.filepath=str(W/(name+'.png'));bpy.ops.render.render(write_still=True)
allparts=set(objects)
render('front_raw',(0,-700,60),(0,100,60),260,(1500,950),allparts)
render('side_raw',(700,95,52),(0,95,52),310,(1500,900),allparts)
render('top_raw',(0,97,700),(0,97,52),350,(1250,1000),allparts)
render('rear_iso',(250,490,240),(0,179,32),190,(720,500),{'rear','battery'})
render('rear_on_head_iso',(300,480,230),(0,147,40),250,(1100,700),{'head','rear','battery','straps','tabs','BTTF','case'})
print('Rear assembly preview renders saved.')
