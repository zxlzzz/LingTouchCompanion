"""Show the actual old and filled rear meshes from the same head-side view."""
from pathlib import Path
import tempfile
import numpy as np
import bpy
from mathutils import Vector
from PIL import Image, ImageDraw

P = Path(__file__).resolve().parent
BASE = P.parent

def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = 16
    scene.cycles.use_denoising = True
    scene.render.resolution_x = 900
    scene.render.resolution_y = 640
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGBA'
    scene.render.film_transparent = True
    scene.view_settings.view_transform = 'AgX'
    world = bpy.data.worlds.new('Neutral studio')
    scene.world = world
    world.use_nodes = True
    world.node_tree.nodes['Background'].inputs['Color'].default_value = (.8,.83,.9,1)
    world.node_tree.nodes['Background'].inputs['Strength'].default_value = .6
    material = bpy.data.materials.new('Neutral unpainted plastic')
    material.use_nodes = True
    shader = material.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value = (.27,.30,.34,1)
    shader.inputs['Roughness'].default_value = .45
    target = Vector((0,210,41))
    camera_data = bpy.data.cameras.new('Same camera')
    camera = bpy.data.objects.new('Same camera',camera_data)
    scene.collection.objects.link(camera)
    camera.location = (105,100,103)
    camera.rotation_euler = (target-camera.location).to_track_quat('-Z','Y').to_euler()
    camera_data.type = 'ORTHO'
    camera_data.ortho_scale = 130
    scene.camera = camera
    for name,location,energy,size in [('Key',(30,110,150),600000,100),('Fill',(-100,180,100),350000,100),('Rim',(20,290,100),500000,80)]:
        light_data = bpy.data.lights.new(name,'AREA')
        light_data.energy = energy
        light_data.shape = 'DISK'
        light_data.size = size
        light = bpy.data.objects.new(name,light_data)
        scene.collection.objects.link(light)
        light.location = location
        light.rotation_euler = (target-light.location).to_track_quat('-Z','Y').to_euler()
    views = []
    with tempfile.TemporaryDirectory(prefix='render_',dir=P) as temporary:
        for index,path in enumerate([BASE/'geometry/rear_body.npz',P/'geometry/rear_body.npz']):
            q = np.load(path)
            mesh = bpy.data.meshes.new('Actual rear triangles')
            mesh.from_pydata(q['v'].tolist(),[],q['f'].tolist())
            mesh.update()
            body = bpy.data.objects.new('Actual rear',mesh)
            scene.collection.objects.link(body)
            mesh.materials.append(material)
            for polygon in mesh.polygons: polygon.use_smooth = True
            mesh.set_sharp_from_angle(angle=np.deg2rad(32))
            output = Path(temporary)/('view'+str(index)+'.png')
            scene.render.filepath = str(output)
            bpy.ops.render.render(write_still=True)
            image = Image.new('RGB',(900,680),'white')
            pixels = Image.open(output).convert('RGBA')
            image.paste(pixels,(0,40),pixels)
            ImageDraw.Draw(image).text((24,15),'Original rear' if index==0 else 'Revised: connector windows and end port filled',fill='black')
            views.append(image)
            bpy.data.objects.remove(body,do_unlink=True)
            bpy.data.meshes.remove(mesh)
        composite = Image.new('RGB',(1800,680),'white')
        composite.paste(views[0],(0,0))
        composite.paste(views[1],(900,0))
        composite.save(P/'Rear_Filled_Comparison.png')

if __name__ == '__main__':
    main()
