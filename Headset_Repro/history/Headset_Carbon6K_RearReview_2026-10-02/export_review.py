"""Export only the new rear candidate, in unchanged wearing coordinates."""
from pathlib import Path
import ast,hashlib,json,zipfile
import xml.etree.ElementTree as ET
import numpy as np
import manifold3d as md

P=Path(__file__).resolve().parent
helper=P.parent/'Headset_ThinShell_Review_2026-10-02/export_review.py'
tree=ast.parse(helper.read_text(encoding='utf8'))
function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='write_review')
exec(compile(ast.Module(body=[function],type_ignores=[]),str(helper),'exec'))
report=write_review(P/'Rear_Carbon6K_Review_Wearing.3mf',
                    P/'geometry/rear_unified_preview.npz','Rear_Carbon6K_review')
(P/'model_verification.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps({k:report[k] for k in ['volume_mm3','bounds_xyz_mm','single_closed_connected_solid','source_mesh_sha256']}))
