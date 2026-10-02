"""Render the supplied reference mesh; no enclosure geometry is generated."""
from pathlib import Path
import bpy
import numpy as np
from mathutils import Vector
from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parent
data = np.load(HERE/'reference_normal_mesh.npz')
bpy.ops.wm.read_factory_settings(use_empty=True)
mesh = bpy.data.meshes.new('Supplied_3MF_Normal')
mesh.from_pydata(data['vertices'].tolist(), [], data['faces'].tolist())
mesh.update()
obj = bpy.data.objects.new('Supplied reference only', mesh)
bpy.context.collection.objects.link(obj)
obj.color = (.52,.58,.64,1)
scene = bpy.context.scene
scene.render.engine = 'BLENDER_WORKBENCH'
scene.display.shading.light = 'STUDIO'
scene.display.shading.studiolight_rotate_z = .4
scene.display.shading.color_type = 'OBJECT'
scene.display.shading.show_shadows = True
scene.display.shading.show_cavity = True
scene.display.shading.cavity_type = 'BOTH'
scene.display.shading.curvature_ridge_factor = 1.3
scene.display.shading.curvature_valley_factor = 1.3
scene.display.shading.show_specular_highlight = True
scene.display.shading.background_type = 'WORLD'
scene.world = bpy.data.worlds.new('Review background')
scene.world.color = (.91,.93,.96)
scene.view_settings.view_transform = 'Standard'
scene.render.resolution_x = 1000
scene.render.resolution_y = 820
scene.render.resolution_percentage = 100
camera_data = bpy.data.cameras.new('Orthographic review')
camera_data.type = 'ORTHO'
camera_data.ortho_scale = 195
camera = bpy.data.objects.new('Review camera', camera_data)
bpy.context.collection.objects.link(camera)
scene.camera = camera
views = [
    ('前视｜原模型', (0,-350,0)),
    ('侧视｜原模型', (350,0,0)),
    ('俯视｜原模型', (0,0,350)),
    ('内侧结构｜原模型', (240,300,230)),
]
paths = []
for i,(title,location) in enumerate(views):
    camera.location = location
    camera.rotation_euler = (-Vector(location)).to_track_quat('-Z','Y').to_euler()
    path = HERE/f'_reference_view_{i}.png'
    paths.append(path)
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
font_path = None
font = ImageFont.load_default(size=32)
small = ImageFont.load_default(size=24)
result = Image.new('RGB',(2000,1810),'#edf1f6')
draw = ImageDraw.Draw(result)
draw.text((42,22),'BTTF 参考模型检查 · 当前文件 Normal 档',font=font,fill='#18293a')
draw.text((42,66),'实际网格外包络：宽 142.31 × 前后长 147.07 × 高 55.18 mm',font=small,fill='#41516a')
for i,((title,_),path) in enumerate(zip(views,paths)):
    x=(i%2)*1000
    y=115+(i//2)*840
    result.paste(Image.open(path).convert('RGB'),(x,y))
    draw.text((x+35,y+12),title,font=font,fill='#18293a')
result.save(HERE/'reference_review.png')
for path in paths:
    path.unlink()
print('REVIEW_RENDER_COMPLETE',str(HERE/'reference_review.png'))
