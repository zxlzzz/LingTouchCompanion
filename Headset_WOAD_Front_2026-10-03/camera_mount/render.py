"""Show the actual added slot, without redesigning the preserved outer shell."""
from pathlib import Path

P=Path(__file__).resolve().parent
template=P.parent/'structural/render.py'
source=template.read_text('utf8')
source=source.replace('P / "structural" / "geometry"','P / "camera_mount" / "geometry"')
source=source.replace('P / "structural" / "views"','P / "camera_mount" / "views"')
source=source.replace("final_views = ('cavity','structure','temples','camera_fit')", """
views['slot_closeup'] = ((-.18,1,.62), {'front'}, 1.7, 1.1, None)
final_views = ('cavity','structure','camera_fit','slot_closeup')""")
exec(compile(source,str(template),'exec'),{'__name__':'__main__','__file__':str(Path(__file__).resolve())})
