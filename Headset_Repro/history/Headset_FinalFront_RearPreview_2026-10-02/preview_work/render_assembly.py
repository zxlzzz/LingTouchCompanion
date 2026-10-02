"""Orthographic review images of actual preview meshes and unchanged head registration."""
from pathlib import Path
import numpy as np
import bpy
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[1]
W=ROOT/'preview_work'
# This approved assembly mesh is independently certified equivalent to the final
# print 3MF in front/verification.json, before its rigid print rotation.
F=ROOT.parent/'Headset_Elastic25_2026-10-02/front_work'
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

def mesh(name,path,color):
    a=np.load(path)
    me=bpy.data.meshes.new(name);me.from_pydata(a['v'].tolist(),[],a['f'].tolist());me.update()
    ob=bpy.data.objects.new(name,me);scene.collection.objects.link(ob)
    ob.color=color;objects[name]=ob
    for poly in me.polygons:poly.use_smooth=True
    me.set_sharp_from_angle(angle=.0872664626)
    return ob

mesh('BTTF',F/'original_modified.npz',(.62,.66,.69,1))
mesh('case',F/'case_material.npz',(.1,.55,.63,1))
mesh('front_tabs',F/'front_tabs.npz',(.1,.55,.63,1))
mesh('camera',F/'camera.npz',(.9,.49,.12,1))
mesh('head',W/'head_display.npz',(.83,.83,.81,.28))
mesh('rear',ROOT/'rear_work/rear_unified_preview.npz',(.49,.33,.68,1))
mesh('straps',ROOT/'connection/straps_preview.npz',(.2,.41,.75,1))
mesh('battery',ROOT/'rear_work/battery_preview.npz',(.83,.77,.91,1))
# Use only the unified mesh in the assembly; isolated real components in the inset.
for name,color in [('rear_tray',(.49,.33,.68,1)),('rear_box',(.49,.33,.68,1)),
                   ('rear_left_rib',(.89,.55,.19,1)),('rear_right_rib',(.89,.55,.19,1)),
                   ('rear_left_ear',(.49,.33,.68,1)),('rear_right_ear',(.49,.33,.68,1)),
                   ('rear_left_ear_root',(.49,.33,.68,1)),('rear_right_ear_root',(.49,.33,.68,1)),
                   ('rear_central_join',(.49,.33,.68,1))]:
    mesh(name,ROOT/'rear_work'/f'{name}.npz',color)
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

assembly={'BTTF','case','front_tabs','camera','head','rear','straps','battery'}
render('front_raw',(0,-700,60),(0,100,60),250,(1400,950),assembly)
render('side_raw',(700,95,52),(0,95,52),310,(1500,900),assembly)
render('top_raw',(0,97,700),(0,97,52),350,(1250,1000),assembly)
rear_components={'rear_tray','rear_box','rear_left_rib','rear_right_rib','rear_left_ear',
                 'rear_right_ear','rear_left_ear_root','rear_right_ear_root','rear_central_join'}
render('rear_iso',(220,40,210),(0,197,32),170,(850,570),rear_components)
render('rear_top',(0,200,700),(0,200,32),165,(1000,650),rear_components)
print('Three assembly views and two insets rendered.')
