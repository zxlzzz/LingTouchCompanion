"""Render the exact delivered front mesh without the removed internal fixtures."""
from pathlib import Path

P=Path(__file__).resolve().parent
template=P.parent/'render.py'
source=template.read_text('utf8')

def replace(old,new):
    global source
    assert source.count(old)==1,old
    source=source.replace(old,new)

replace('G = P / "geometry"','G = P / "structural" / "geometry"')
replace('W = P / "views"','W = P / "structural" / "views"')
replace('mesh("retention_band", G / "retention_band.npz", "band")','')
replace('"shell": material("black satin printed shell", (.026, .029, .034), .30)',
        '"shell": material("gray inspection shell", (.28, .31, .35), .48)')
replace('final_views = ("woad_front_angle", "woad_inside_angle", "worn_side")', '''
views['cavity'] = ((-.25,.9,-.4), {'front'}, 1.5, 1.12, None)
views['structure'] = ((-.45,.88,.60), {'front'}, 1.5, 1.12, None)
views['temples'] = ((0,0,1), {'front'}, 1.1, 1.1, None)
views['camera_fit'] = ((.55,-.8,.45), {'front','camera'}, 1.5, 1.12, None)
final_views = ('cavity','structure','temples','camera_fit')''')
exec(compile(source,str(template),'exec'),{'__name__':'__main__','__file__':str(template)})
