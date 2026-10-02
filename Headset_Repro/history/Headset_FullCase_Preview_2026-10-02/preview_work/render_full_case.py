from pathlib import Path
import numpy as np
import bpy
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1];W=ROOT/'preview_work'
bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene
scene.render.engine='BLENDER_WORKBENCH';scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.world=bpy.data.worlds.new('white');scene.world.color=(1,1,1)
sh=scene.display.shading;sh.light='STUDIO';sh.color_type='OBJECT';sh.studiolight_rotate_z=.4
sh.show_shadows=True;sh.show_cavity=True;sh.cavity_type='BOTH';sh.show_object_outline=True
sh.object_outline_color=(.17,.22,.25);sh.background_type='WORLD'
scene.view_settings.view_transform='Standard';scene.view_settings.look='None'
colors={'original_modified':(.65,.69,.73,1),'camera':(.92,.51,.12,1),
        'case_material':(.1,.56,.64,1),'front_tabs':(.1,.56,.64,1),
        'pocket':(.51,.35,.70,1),'battery':(.86,.77,.93,1)}
obs={}
for n,col in colors.items():
 a=np.load(W/(n+'.npz'));me=bpy.data.meshes.new(n);me.from_pydata(a['v'].tolist(),[],a['f'].tolist());me.update()
 ob=bpy.data.objects.new(n,me);scene.collection.objects.link(ob);ob.color=col;obs[n]=ob
 if n=='case_material':
  for poly in me.polygons:poly.use_smooth=True
  me.set_sharp_from_angle(angle=.0872664626)
data=bpy.data.cameras.new('orthographic');cam=bpy.data.objects.new('orthographic',data)
scene.collection.objects.link(cam);scene.camera=cam;data.type='ORTHO';data.clip_end=3000;data.clip_start=.01
def render(n,pos,target,scale,size,show):
 for name,ob in obs.items():ob.hide_render=name not in show
 cam.location=pos;cam.rotation_euler=(Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler()
 data.ortho_scale=scale;scene.render.resolution_x,scene.render.resolution_y=size
 scene.render.filepath=str(W/(n+'.png'));bpy.ops.render.render(write_still=True)
front={'original_modified','camera','case_material','front_tabs'};allparts=set(obs)
render('front_raw',(0,-650,27.6),(0,20,27.6),166,(1500,660),front)
render('side_raw',(700,85,28),(0,85,28),275,(1500,540),allparts)
render('top_raw',(0,85,700),(0,85,0),285,(900,1000),allparts)
render('pocket_iso',(210,-60,170),(0,199.8,24),170,(650,340),{'pocket'})
render('front_iso',(230,-250,170),(0,32,27),240,(650,340),front)
render('rear_detail',(0,170,34),(0,0,34),108,(700,370),{'original_modified','camera','case_material'})
print('Full-case orthographic previews rendered.')
