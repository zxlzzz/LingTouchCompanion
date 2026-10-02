from pathlib import Path
import math
import numpy as np
import bpy
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1]
WORK=ROOT/'preview_work'
bpy.ops.wm.read_factory_settings(use_empty=True)
scene=bpy.context.scene
scene.render.engine='BLENDER_WORKBENCH'
scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG'
scene.world=bpy.data.worlds.new('white')
scene.world.color=(1,1,1)
scene.display.shading.light='STUDIO'
scene.display.shading.studiolight_rotate_z=.4
scene.display.shading.color_type='OBJECT'
scene.display.shading.show_shadows=True
scene.display.shading.show_cavity=True
scene.display.shading.cavity_type='BOTH'
scene.display.shading.show_object_outline=True
scene.display.shading.object_outline_color=(.15,.20,.24)
scene.display.shading.background_type='WORLD'
scene.view_settings.view_transform='Standard'
scene.view_settings.look='None'
colors={'original':(.64,.68,.73,1),'camera':(.92,.51,.12,1),
        'socket':(.09,.56,.65,1),'required_fill_diagnostic':(.85,.24,.24,1),
        'front_tabs':(.09,.56,.65,1),'pocket':(.52,.35,.70,1),'battery':(.86,.77,.93,1)}
objects={}
for name in colors:
 a=np.load(WORK/(name+'.npz'))
 me=bpy.data.meshes.new(name);me.from_pydata(a['v'].tolist(),[],a['f'].tolist());me.update()
 ob=bpy.data.objects.new(name,me);scene.collection.objects.link(ob);ob.color=colors[name];objects[name]=ob
camdata=bpy.data.cameras.new('orthographic');cam=bpy.data.objects.new('orthographic',camdata)
scene.collection.objects.link(cam);scene.camera=cam;camdata.type='ORTHO';camdata.clip_end=3000;camdata.clip_start=.01
def render(name,pos,target,scale,size,show):
 for n,o in objects.items():o.hide_render=n not in show
 cam.location=pos;cam.rotation_euler=(Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler()
 camdata.ortho_scale=scale;scene.render.resolution_x=size[0];scene.render.resolution_y=size[1]
 scene.render.filepath=str(WORK/(name+'.png'));bpy.ops.render.render(write_still=True)
front={'original','camera','socket','required_fill_diagnostic','front_tabs'}
allparts=set(objects)-{'battery'}
render('front_raw',(0,-650,27.6),(0,20,27.6),166,(1500,660),front)
render('side_raw',(700,85,28),(0,85,28),275,(1500,540),allparts|{'battery'})
render('top_raw',(0,85,700),(0,85,0),285,(900,1000),allparts|{'battery'})
render('pocket_iso',(210,-60,170),(0,199.8,24),170,(700,360),{'pocket'})
render('front_iso',(230,-250,180),(0,32,27),185,(700,360),front)
print('Rendered preview views. No print files exported.')
