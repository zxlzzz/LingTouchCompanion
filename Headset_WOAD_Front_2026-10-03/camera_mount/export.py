"""Reuse the proven native Bambu exporter for the additive camera-slot revision."""
from pathlib import Path
import json

P=Path(__file__).resolve().parent
template=P.parent/'structural/export.py'
source=template.read_text('utf8')
for old,new in [('Front_Simple_Print.3mf','Front_CS30_Mount_Print.3mf'),
                ('Front_Simple_Wearing.3mf','Front_CS30_Mount_Wearing.3mf'),
                ('Front_Simple_One_Piece','Front_CS30_Mount_One_Piece'),
                ('Simple one-piece front | print','One-piece front with CS30 slot | print'),
                ('Simple front | fit reference','CS30 slot | fit reference')]:
    assert old in source,old
    source=source.replace(old,new)
exec(compile(source,str(template),'exec'),{'__name__':'__main__','__file__':str(Path(__file__).resolve())})
