"""Separately saved front: straight temple spans and integrated nose saddle.

The preceding generator is reused without editing it. Existing 3MF files and
the original camera/head/strap inputs are never overwritten.
"""
from pathlib import Path
import hashlib, importlib.util, json
import numpy as np

P = Path(__file__).resolve().parent
BASE = P.parent
ROOT = BASE.parent
G = P/'geometry'

def module(path, name):
    spec=importlib.util.spec_from_file_location(name,path)
    result=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    G.mkdir(parents=True,exist_ok=True)
    (P/'checks').mkdir(exist_ok=True)
    finished={str(p.relative_to(ROOT)).replace('\\','/'):digest(p) for p in ROOT.glob('Headset_*/*.3mf')}
    base=module(BASE/'build.py','previous_front_generator')
    base.G=G
    base.ARM_START_X=88.4
    def straight_sections(side,head):
        tab=base.DATUMS['terminal_left_x' if side<0 else 'terminal_right_x']
        end_x=abs(np.mean(tab))
        rows=[]
        for y in np.linspace(43,base.DATUMS['terminal_reach_y'],234):
            # One straight main span; a short, monotone inward return preserves
            # the existing terminal slot in all three coordinates.
            transition=base.smooth((y-130)/20)
            x=88.4*(1-transition)+end_x*transition
            terminal=base.smooth((y-143)/7)
            w=3.4*(1-terminal)+(tab[1]-tab[0])*terminal
            low=35.0*(1-terminal)+23.2*terminal
            oldtop=47.0*(1-terminal)+55.2*terminal
            top=base.print_top(y)+.7
            rows.append((y,x,w,low,oldtop,top))
        return rows
    base.arm_sections=straight_sections
    base.build()
    q=np.load(G/'front_body.npz')
    body=base.mesh(q['v'],q['f'])
    head=base.HeadSurface()
    xs=np.linspace(-14,14,113)
    zs=np.linspace(15.5,26,85)
    # The wide nose saddle follows the true nasal skin. 0.02 mm compensates
    # tessellation at contact; it is not a comfort stand-off or fitted camera.
    contact=base.skin_cutter(head,.02,xs,zs)
    forward=base.skin_cutter(head,2.22,xs,zs)
    saddle=(forward-contact)^base.xz_prism(base.rounded(26,9.0,2.5,(0,20.6)),-10,35)
    bridge=base.xz_prism(base.rounded(26,1.8,.5,(0,24.3)),-2,35)-contact
    nose=base.union([saddle,bridge])
    combined=body+nose
    assert len(combined.decompose())==1,'Nose saddle not joined to shell'
    result=base.save('front_body',combined,base.paint)
    pad=base.save('nose_support',nose)
    values=json.loads((G/'geometry_values.json').read_text('utf8'))
    values['geometry']['front_body']=result
    values['nose_support']={'width_mm':26,'height_mm':9,'front_to_back_sheet_mm':2.2,
        'skin_tessellation_compensation_mm':.02,'bounds_xyz_mm':pad['bounds_xyz_mm'],
        'additional_union_volume_cm3':float((combined-body).volume())/1000,
        'construction':'Broad curved integral saddle and short floor extension, wholly below the actual camera.'}
    values['temple_revision']={'straight_main_span_y_mm':[43,130],'straight_center_abs_x_mm':88.4,
        'terminal_return_y_mm':[130,150],'terminal_slot_xyz_preserved':True,
        'note':'Parallel straight main spans; only one smooth inward terminal return. No lateral ripple follows the ears.'}
    values['previous_finished_3mf_sha256']=finished
    values['generator_sha256']={'revision':digest(Path(__file__)), 'unchanged_template':digest(BASE/'build.py')}
    (G/'geometry_values.json').write_text(json.dumps(values,indent=2),encoding='utf8')
    assert all(digest(ROOT/p)==sha for p,sha in finished.items())
    print(json.dumps({'front':result,'nose':values['nose_support'],'temples':values['temple_revision'],
                      'previous_3mf_untouched':True},indent=2),flush=True)

if __name__=='__main__':main()
