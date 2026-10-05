"""Add only a plain CS30 locating slot to the preserved one-piece front."""
from pathlib import Path
import hashlib
import importlib.util
import json
import shutil
import numpy as np

P=Path(__file__).resolve().parent
BASE=P.parent
ROOT=BASE.parent
SOURCE=BASE/'structural'
G=P/'geometry'


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    G.mkdir(parents=True,exist_ok=True)
    (P/'checks').mkdir(exist_ok=True)
    spec=importlib.util.spec_from_file_location('geometry_methods',BASE/'build.py')
    b=importlib.util.module_from_spec(spec);spec.loader.exec_module(b);b.G=G
    old={str(p.relative_to(ROOT)).replace('\\','/'):digest(p)
         for p in ROOT.glob('Headset_*/**/*.3mf') if P not in p.parents}
    q=np.load(SOURCE/'geometry/front_body.npz'); body=b.mesh(q['v'],q['f'])
    cam=np.load(SOURCE/'geometry/camera.npz')
    used=cam['v'][np.unique(cam['f'])]
    low,high=used.min(0),used.max(0)
    gap=.3; wall=1.6
    x0,x1=low[0]-gap,high[0]+gap
    yf=low[1]-gap; floor_end=3.8
    seat_z=float(low[2])-1e-5
    bottom=23.3
    # Flat bearing surface and short plain walls. These do not enclose the
    # camera's upper half and are not joined to the external forehead roof.
    pieces=[b.box([x0-wall,yf-wall,bottom],[x1+wall,floor_end,seat_z]),
            b.box([x0-wall,yf-wall,bottom],[x0,floor_end,38.5]),
            b.box([x1,yf-wall,bottom],[x1+wall,floor_end,38.5]),
            b.box([x0,yf-wall,bottom],[x1,yf,seat_z+3.0])]
    for xa,xb in [(-32,-15),(15,32)]:
        pieces.append(b.box([xa,3.6,bottom],[xb,6.5,seat_z]))
        pieces.append(b.box([xa,4.9,bottom],[xb,6.5,seat_z+.8]))
    # Keep all new plastic inside the established curved housing envelope;
    # the locating floor must not become a rectangular slab below the shell.
    envelope=b.loft([b.profile(x) for x in np.linspace(-66,66,281)]) ^ b.below_print_plane()
    mount=b.union(pieces)^envelope
    combined=body+mount
    assert len(combined.decompose())==1,'Mount must be integral with front'
    added=combined-body
    info=b.save('front_body',combined,b.paint)
    mount_info=b.save('mount_added',added)
    for name in ['camera','camera_optics','nose_support','connection_straps']:
        shutil.copy2(SOURCE/'geometry'/(name+'.npz'),G/(name+'.npz'))
    values=json.loads((SOURCE/'geometry/geometry_values.json').read_text('utf8'))
    values['geometry']={'front_body':info,'mount_added':mount_info}
    values['retention']='The simple slot supports the camera below and locates it laterally and forward. Two low rear lips restrict seated rearward sliding; lift 1.2 mm before sliding through the rear opening. No strap or snap is added.'
    values['mount']={'camera_bounds_xyz_mm':[low.tolist(),high.tolist()],
        'inner_x_mm':[float(x0),float(x1)],'side_clearance_each_mm':gap,
        'front_stop_inner_y_mm':float(yf),'front_clearance_mm':gap,
        'floor_top_z_mm':seat_z,'floor_rear_y_mm':floor_end,
        'side_wall_top_z_mm':38.5,'wall_thickness_mm':wall,
        'front_stop_height_mm':3.,'rear_lip_height_mm':.8,
        'rear_lips_x_mm':[[-32,-15],[15,32]],'rear_lips_y_mm':[4.9,6.5],
        'installation_lift_mm':1.2,'installation_translation_direction':[0,-1,0],
        'added_volume_cm3':float(added.volume())/1000,
        'outer_profile_preserved':True,
        'limitations':'The rigid geometry locates a seated camera. Print fit and retention under handling require a physical fit test; this is not a positive-lock latch.'}
    values['previous_finished_3mf_sha256']=old
    values['source_sha256']={str(p.relative_to(ROOT)).replace('\\','/'):digest(p)
        for p in [Path(__file__),SOURCE/'geometry/front_body.npz',SOURCE/'geometry/camera.npz']}
    (G/'geometry_values.json').write_text(json.dumps(values,indent=2),encoding='utf8')
    assert float((body-combined).volume())<1e-7
    assert all(digest(ROOT/p)==h for p,h in old.items())
    print(json.dumps({'body':info,'mount':values['mount']},indent=2),flush=True)


if __name__=='__main__':main()
