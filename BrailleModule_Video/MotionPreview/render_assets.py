"""Render actual axial pin displacement in the approved photographic scene.

The interactive fixed-camera preview uses these pin-local RGB image sequences.
ModuleMotion.blend is the independently editable 3D animation deliverable.
"""
from pathlib import Path
import hashlib
import json
import math

import bpy
import numpy as np
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view
from PIL import Image, ImageOps

P=Path(__file__).resolve().parent
ASSETS=P/'assets'
WORK=P/'.work'
ASSETS.mkdir(exist_ok=True)
WORK.mkdir(exist_ok=True)
SOURCE=P/'AppearanceStudy.blend'
HEIGHTS=[0,.05,.10,.15,.20,.25,.30,.35,.40,.45,.50,.55,.60,.65,.675,.70]
WIDTH,HEIGHT=1280,720
SAMPLES=64
M=.001
MOTION=json.loads((ASSETS/'motion.json').read_text(encoding='utf8'))

bpy.ops.wm.open_mainfile(filepath=str(SOURCE))
scene=bpy.context.scene
scene.camera=bpy.data.objects['Video closeup camera']
scene.render.resolution_x=WIDTH
scene.render.resolution_y=HEIGHT
scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG'
scene.render.image_settings.color_mode='RGB'
scene.render.image_settings.color_depth='8'
scene.render.use_compositing=False
scene.render.use_sequencer=False
scene.render.film_transparent=False
scene.render.use_persistent_data=True
scene.cycles.samples=SAMPLES
scene.cycles.use_denoising=True
scene.cycles.seed=0
scene.cycles.use_animated_seed=False
pref=bpy.context.preferences.addons['cycles'].preferences
pref.compute_device_type='OPTIX'
pref.get_devices()
for device in pref.devices: device.use=device.type=='OPTIX'
scene.cycles.device='GPU'
dots=[bpy.data.objects[f'Dot_{i}'] for i in range(1,7)]
rest=[o.location.copy() for o in dots]

def reset():
    for o,pos in zip(dots,rest): o.location=pos
    bpy.context.view_layer.update()

def render(path,box=None):
    # Keep the full camera gate; only restrict Cycles' sampled pixel region.
    if box is None:
        scene.render.use_border=False
        scene.render.use_crop_to_border=False
        scene.render.border_min_x=scene.render.border_min_y=0.0
        scene.render.border_max_x=scene.render.border_max_y=1.0
        expected_size=(WIDTH,HEIGHT)
    else:
        x0,y0,x1,y1=box
        assert 0<=x0<x1<=WIDTH and 0<=y0<y1<=HEIGHT
        # Blender truncates normalized border coordinates to integer pixels.
        # A 0.001-pixel positive bias prevents float32 values falling below
        # their intended integer boundary without changing the sampled ROI.
        def boundary(pixel,dimension):
            return min(1.0,(pixel+.001)/dimension)
        scene.render.use_border=True
        scene.render.use_crop_to_border=True
        scene.render.border_min_x=boundary(x0,WIDTH)
        scene.render.border_max_x=boundary(x1,WIDTH)
        scene.render.border_min_y=boundary(HEIGHT-y1,HEIGHT)
        scene.render.border_max_y=boundary(HEIGHT-y0,HEIGHT)
        expected_size=(x1-x0,y1-y0)
    scene.render.filepath=str(path)
    bpy.ops.render.render(write_still=True)
    image=Image.open(path).convert('RGB')
    assert image.size==expected_size, (image.size,expected_size,box)
    return image

reset()
base=render(ASSETS/'Base.png')
manifest={'image':{'width':WIDTH,'height':HEIGHT},'heights_mm':HEIGHTS,
          'motion':MOTION,
          'dots':[],'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
          'scope':'Fixed photographic camera; heights and timings are provisional visual settings.'}
pixel_boxes=[]
layer_stills={}
for number,(o,pos) in enumerate(zip(dots,rest),1):
    points=[]
    for h in [0,.70]:
        o.location.z=pos.z+h*M
        bpy.context.view_layer.update()
        for v in o.bound_box:
            s=world_to_camera_view(scene,scene.camera,o.matrix_world@Vector(v))
            points.append((s.x*WIDTH,(1-s.y)*HEIGHT))
    reset()
    margin=20
    x0=max(0,math.floor(min(p[0] for p in points))-margin)
    y0=max(0,math.floor(min(p[1] for p in points))-margin)
    x1=min(WIDTH,math.ceil(max(p[0] for p in points))+margin)
    y1=min(HEIGHT,math.ceil(max(p[1] for p in points))+margin)
    w,h=x1-x0,y1-y0
    tw,th=w+4,h+4
    atlas=Image.new('RGB',(tw*4,th*4))
    for level,height in enumerate(HEIGHTS):
        o.location.z=pos.z+height*M
        bpy.context.view_layer.update()
        crop=base.crop((x0,y0,x1,y1)) if level==0 else render(WORK/'height.png',(x0,y0,x1,y1))
        assert crop.size==(w,h)
        padded=ImageOps.expand(crop,border=2)
        # Repeat edge pixels into gutters to prevent neighbouring tile leakage.
        padded.paste(crop.crop((0,0,w,1)).resize((w,2)),(2,0))
        padded.paste(crop.crop((0,h-1,w,h)).resize((w,2)),(2,h+2))
        padded.paste(crop.crop((0,0,1,h)).resize((2,h)),(0,2))
        padded.paste(crop.crop((w-1,0,w,h)).resize((2,h)),(w+2,2))
        for xx,yy,px,py in [(0,0,0,0),(w+2,0,w-1,0),(0,h+2,0,h-1),(w+2,h+2,w-1,h-1)]:
            padded.paste(crop.getpixel((px,py)),(xx,yy,xx+2,yy+2))
        atlas.paste(padded,((level%4)*tw,(level//4)*th))
        if height in [.45,.70]: layer_stills[number,height]=np.asarray(crop).copy()
        print(f'Dot {number}: height {height:.3f} mm ({level+1}/16)',flush=True)
    atlas.save(ASSETS/f'dot_{number}.png',optimize=True)
    reset()
    centre=world_to_camera_view(scene,scene.camera,o.matrix_world@Vector((0,0,0)))
    manifest['dots'].append({'number':number,'atlas':f'dot_{number}.png','rect':[x0,y0,w,h],
                             'tile':[tw,th],'columns':4,'rows':4,
                             'centre':[round(centre.x*WIDTH,2),round((1-centre.y)*HEIGHT,2)]})
    pixel_boxes.append((x0,y0,x1,y1))
    (ASSETS/'manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf8')

def linear(rgb):
    x=np.asarray(rgb,dtype=np.float64)/255
    return np.where(x<=.04045,x/12.92,((x+.055)/1.055)**2.4)
def srgb(x):
    x=np.maximum(x,0)
    return np.clip(np.where(x<=.0031308,x*12.92,1.055*x**(1/2.4)-.055),0,1)*255

checks=[]
for height,name in [(.70,'Peak'),(.45,'Hold')]:
    reset()
    for o,pos in zip(dots,rest): o.location.z=pos.z+height*M
    bpy.context.view_layer.update()
    full=render(P/(name+'.png'))
    composed=linear(base)
    for number,rect in enumerate(pixel_boxes,1):
        x0,y0,x1,y1=rect
        composed[y0:y1,x0:x1]+=linear(layer_stills[number,height])-linear(base.crop(rect))
    composed=srgb(composed)
    full_array=np.asarray(full,dtype=np.float64)
    # Compare photographic image composition against a simultaneous genuine render.
    delta=np.abs(composed-full_array)
    foreground=delta[np.any(delta>1,axis=2)]
    checks.append({'height_mm':height,'mean_channel_error_255':round(float(delta.mean()),3),
                   'p99_channel_error_255':round(float(np.quantile(delta,.99)),3),
                   'fraction_pixels_over_10':round(float(np.mean(np.max(delta,axis=2)>10)),5)})
    Image.fromarray(np.rint(composed).astype(np.uint8)).save(WORK/(name+'_composed.png'))
reset()
(P/'RenderVerification.json').write_text(json.dumps({'rendered_levels_per_dot':len(HEIGHTS),
     'independent_dots':6,'combined_render_comparisons':checks,
     'appearance_scene_sha256':manifest['source_sha256'],
     'approved_static_scene_sha256':hashlib.sha256((P.parent/'PhotoStudy'/'ReferenceStudy.blend').read_bytes()).hexdigest(),
     'peak_mm':.70,'hold_mm':.45,'bottom_stem_overlap_at_peak_mm':.15,
     'motion_direction':'Each independent dot local +Z; no shape scaling',
     'source_scene_not_modified':True},indent=2),encoding='utf8')
print('Motion appearance assets completed.',flush=True)
