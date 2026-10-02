import bpy,sys,numpy as np
from pathlib import Path
from mathutils import Vector
D=Path(__file__).parent.parent/sys.argv[1];bpy.ops.wm.open_mainfile(filepath=str(D/(sys.argv[2] if len(sys.argv)>2 else 'working.blend')),load_ui=False,use_scripts=False)
s=bpy.context.scene;s.render.engine='BLENDER_WORKBENCH';s.display.shading.light='STUDIO';s.display.shading.color_type='MATERIAL';s.display.shading.show_shadows=True;s.display.shading.show_cavity=True;s.display.shading.cavity_type='BOTH';s.display.shading.background_type='WORLD';s.world.color=(.9,.92,.94);s.render.film_transparent=False
s.render.resolution_x=1200;s.render.resolution_y=1000;s.render.resolution_percentage=70
c=bpy.data.objects['VIEW_ISO'];c.location=(440,610,340);target=Vector((0,0,35));c.rotation_euler=(target-c.location).to_track_quat('-Z','Y').to_euler();c.data.ortho_scale=330;s.camera=c
s.render.filepath=str(D/'preview.png');bpy.ops.render.render(write_still=True)
