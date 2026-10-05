"""One-piece front with an empty cavity and ordinary solid temple connections.

Preserves the actual camera, nose saddle, optical face, and headband datums.
The rejected internal plates/eyes/stops and the elevated temple channels are
not constructed. Prior delivered files are read-only inputs.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import shutil
import numpy as np

P = Path(__file__).resolve().parent
BASE = P.parent
ROOT = BASE.parent
G = P / 'geometry'


def module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def terminal_top(y):
    """A straight flare with short tangent transitions at both ends."""
    t = float(np.clip((y-110)/40,0,1))
    a = .15
    q = (t*t/(2*a*(1-a)) if t<a else
         1-(1-t)**2/(2*a*(1-a)) if t>1-a else (t-a/2)/(1-a))
    return 47+8.2*q


def main():
    G.mkdir(parents=True, exist_ok=True)
    (P / 'checks').mkdir(exist_ok=True)
    old = {str(p.relative_to(ROOT)).replace('\\', '/'): digest(p)
           for p in ROOT.glob('Headset_*/**/*.3mf') if P not in p.parents}
    b = module(BASE / 'build.py', 'preserved_geometry_methods')
    b.G = G
    head = b.HeadSurface()
    outer = b.loft([b.profile(x) for x in np.linspace(-66, 66, 281)]) ^ b.below_print_plane()
    inner_x = np.r_[-67., np.linspace(-66,66,281), 67.]
    inner = b.loft([b.profile(x, True) for x in inner_x]) ^ b.below_print_plane(b.WALL)
    skin = b.skin_cutter(head)
    shell = outer - inner - (skin ^ b.box([-100, -100, 0], [100, 43, 100]))
    shell -= b.xz_prism(b.rounded(143.5, 41.2, 1., (0, 45.4)), b.REAR_Y - .8, 100)

    # Single curved strips attach at the ends of the front panel. They have
    # no inner panel, channel, horizontal shelf, or separate collar.
    connections = []
    for side in (-1, 1):
        rows = []
        start_x, end_x = 65.5, 88.4
        start_y = b.front_y(66) + 1.65
        for t in np.linspace(0, 1, 121):
            angle = t * np.pi / 2
            theta = np.arctan2((43-start_y)*np.sin(angle), (end_x-start_x)*np.cos(angle))
            s = b.smooth(t)
            x = start_x + (end_x-start_x)*np.sin(angle)
            y = start_y + (43-start_y)*(1-np.cos(angle))
            low = 26.0*(1-s) + 35.0*s
            top = b.print_top(start_y)*(1-s) + 47.0*s
            local = b.section(3.4, top-low, [1.65]*4)
            rows.append([[side*(x-a*np.sin(theta)), y+a*np.cos(theta), (low+top)/2+z] for a,z in local])
        connections.append(b.loft(rows))
        tab = b.DATUMS['terminal_left_x' if side < 0 else 'terminal_right_x']
        rows = []
        for y in np.linspace(42.8, b.DATUMS['terminal_reach_y'], 240):
            s = b.smooth((y-130)/20)
            x = 88.4*(1-s) + abs(np.mean(tab))*s
            end = b.smooth((y-143)/7)
            width = 3.4*(1-end) + (tab[1]-tab[0])*end
            # A 40 mm flare with 6 mm tangent blends has max rise 0.2412
            # mm/mm. In the 135-degree pose its underside stays above31deg,
            # including the transition into the unchanged headband terminal.
            low, top = 35*(1-end)+23.2*end, terminal_top(y)
            radius = min(width/2-.01, (top-low)/2-.01)
            rows.append([[side*(x-a), y, (low+top)/2+z]
                         for a,z in b.section(width, top-low, [radius]*4)])
        connections.append(b.loft(rows))
    body = b.union([shell, *connections])

    # Keep the established external forehead roof and nose bearing surface.
    xs, zs = np.linspace(-48,48,385), np.linspace(24,72,193)
    contact_skin = b.skin_cutter(head, .02, xs, zs)
    roof = b.loft([[[x,2,b.print_top(2)-b.WALL*np.sqrt(1+b.PRINT_SLOPE**2)],
                   [x,45,b.print_top(45)-b.WALL*np.sqrt(1+b.PRINT_SLOPE**2)],
                   [x,45,b.print_top(45)], [x,2,b.print_top(2)]]
                  for x in np.linspace(-47,47,189)]) - contact_skin
    lip = ((b.skin_cutter(head,1.22,xs,zs)-contact_skin)
           ^ b.box([-47,-100,57],[47,45,80]) ^ b.below_print_plane())
    q = np.load(BASE / 'revised/geometry/nose_support.npz')
    nose = b.mesh(q['v'],q['f'])
    body = b.union([body, roof, lip, nose])

    for side in (-1,1):
        tab = b.DATUMS['terminal_left_x' if side < 0 else 'terminal_right_x']
        y0,y1 = b.DATUMS['terminal_slot_y']; z0,z1 = b.DATUMS['terminal_slot_z']
        body -= b.box([tab[0]-5,y0,z0],[tab[1]+5,y1,z1])

    oval = b.rounded(90,28,14,(0,b.OVAL_CENTER_Z))
    ring = oval-oval.offset(-1,circular_segments=96)
    slab = b.loft([[[x,b.front_y(x)-5,25], [x,b.front_y(x)+.28,25],
                    [x,b.front_y(x)+.28,57], [x,b.front_y(x)-5,57]]
                   for x in np.linspace(-46,46,185)])
    body -= b.xz_prism(ring,-40,0)^slab
    original_values = json.loads((BASE/'revised/geometry/geometry_values.json').read_text('utf8'))
    optics = original_values['optics']
    body -= b.union([b.cylinder_y(o['x'],38,-40,20,o['opening_mm'][0]/2)
                     if o['name'] != 'TX' else
                     b.xz_prism(b.rounded(9,6.5,1,(o['x'],38)),-40,20) for o in optics])
    # Flatten 0.5 mm of the existing rounded front rim. This gives the one-piece
    # body a real print contact face, rather than relying on a tangent line.
    angle = np.deg2rad(135)
    rotation = np.array([[1,0,0],[0,np.cos(angle),-np.sin(angle)],
                         [0,np.sin(angle),np.cos(angle)]])
    rotated = body.transform(np.column_stack([rotation,np.zeros(3)]))
    bottom = float(rotated.bounding_box()[2])
    trim_depth = .5
    contact_area = rotated.slice(bottom+trim_depth).area()
    rotated ^= b.box([-500,-500,bottom+trim_depth],[500,500,500])
    body = rotated.transform(np.column_stack([rotation.T,np.zeros(3)]))
    assert len(body.decompose()) == 1, [(p.volume(),p.bounding_box()) for p in body.decompose()]
    info = b.save('front_body', body, b.paint)
    for name in ['camera','camera_optics','nose_support','connection_straps']:
        shutil.copy2(BASE/'revised/geometry'/(name+'.npz'), G/(name+'.npz'))
    values = {key: original_values[key] for key in ['camera_transform_native_to_wearing','camera_orientation',
              'camera_rear_y_mm','camera_bottom_z_mm','shell_wall_mm','optics','nose_support']}
    values.update({'geometry': {'front_body':info}, 'head_audit_parts':['front_body','camera'],
        'removed_features':['Both internal cheek plates','Both internal strap-eye blocks',
            'All four internal seating stops','Both elevated temple channel structures',
            'Hollow shoulder collars'],
        'temple_main_section_mm':{'y':[43,110],'abs_x_center':88.4,'width':3.4,'z':[35,47]},
        'terminal_upper_flare':{'y_mm':[110,150],'z_mm':[47,55.2],
            'end_blend_length_mm':6,'max_rise_mm_per_mm':8.2/34},
        'connections':'One solid curved strip per side; no channel or cavity inside the connection.',
        'print_foot':{'rotation_about_wearing_x_deg':135,'trim_depth_mm':trim_depth,
            'untrimmed_print_z_min':bottom,'flat_area_mm2':float(contact_area),
            'construction':'A plane removes 0.5 mm from the existing rounded outer rim; no added tab, joint, or separate component.'},
        'retention':'The internal camera strap eyes were removed with the rejected structures. No camera fixation is claimed; the headband terminal holes remain.',
        'previous_finished_3mf_sha256':old,
        'source_sha256':{str(p.relative_to(ROOT)).replace('\\','/'):digest(p) for p in
            [Path(__file__), BASE/'build.py',BASE/'revised/geometry/nose_support.npz']}})
    (G/'geometry_values.json').write_text(json.dumps(values,indent=2),encoding='utf8')
    assert all(digest(ROOT/p)==h for p,h in old.items())
    print(json.dumps(info,indent=2),flush=True)


if __name__ == '__main__':
    main()
