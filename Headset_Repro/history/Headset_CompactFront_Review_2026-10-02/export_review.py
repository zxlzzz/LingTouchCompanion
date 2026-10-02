from pathlib import Path
import ast,hashlib,json,zipfile
import xml.etree.ElementTree as ET
import numpy as np
import manifold3d as md
P=Path(__file__).resolve().parent
helper=P.parent/'Headset_Carbon6K_FlatBase_Review_2026-10-02/inputs/write_review.py'
tree=ast.parse(helper.read_text(encoding='utf8'))
function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='write_review')
exec(compile(ast.Module(body=[function],type_ignores=[]),str(helper),'exec'))
r=write_review(P/'Front_Compact_Review_Wearing.3mf',P/'geometry/front_unified_preview.npz','Front_compact_review')
(P/'model_verification.json').write_text(json.dumps(r,indent=2),encoding='utf8')
print(json.dumps(r,indent=2))
