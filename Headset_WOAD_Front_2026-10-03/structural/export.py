"""Export one printable body, the wearing assembly, and saved actual settings."""
from pathlib import Path
import importlib.util
import json
import math
import zipfile
import xml.etree.ElementTree as ET
import numpy as np

P = Path(__file__).resolve().parent
BASE = P.parent
ROOT = BASE.parent
G = P/'geometry'


def main():
    spec = importlib.util.spec_from_file_location('archive_methods', BASE/'printable/export.py')
    e = importlib.util.module_from_spec(spec); spec.loader.exec_module(e)
    v,f = e.load(G/'front_body.npz')
    a = math.radians(135)
    rotation = np.array([[1,0,0],[0,math.cos(a),-math.sin(a)],[0,math.sin(a),math.cos(a)]])
    posed = v@rotation.T
    translation = np.r_[128-(posed[:,:2].min(0)+posed[:,:2].max(0))/2, -posed[:,2].min()]
    posed += translation
    assert np.all(posed[:,:2].min(0)>10) and np.all(posed[:,:2].max(0)<246)
    np.savez_compressed(G/'front_print.npz',v=posed,f=f)
    path=P/'Front_Simple_Print.3mf'
    print_report=e.archive(path,[('Front_Simple_One_Piece',posed,f,True,0)],'Simple one-piece front | print')
    source=BASE/'camera_mount/project_settings.json'
    settings=json.loads(source.read_text('utf8'))
    source_metadata=json.loads((BASE/'camera_mount/project_metadata.json').read_text('utf8'))
    # Native Bambu import needs application/version markers as well as the
    # embedded config. Copy only those markers, never prior object metadata.
    with zipfile.ZipFile(path) as output:
        members={name:output.read(name) for name in output.namelist()}
    model=ET.fromstring(members['3D/3dmodel.model'])
    for key in ['Application','BambuStudio:3mfVersion']:
        node=ET.Element(e.tag('metadata'),name=key); node.text=source_metadata[key]
        model.insert(0,node)
    members['3D/3dmodel.model']=ET.tostring(model,encoding='UTF-8',xml_declaration=True)
    members['Metadata/project_settings.config']=json.dumps(settings,indent=2).encode('utf8')
    with zipfile.ZipFile(path,'w',compression=zipfile.ZIP_DEFLATED) as output:
        for name,data in members.items(): output.writestr(name,data)
    print_report['sha256']=e.sha(path)
    wearing=[('Front_Simple_One_Piece',v,f,True,0)]
    for name,filename,material in [('Camera_REFERENCE_ONLY',G/'camera.npz',2),
                                  ('Head_REFERENCE_ONLY',ROOT/'Headset_Inputs/Medium_Trial_Registered.npz',1)]:
        rv,rf=e.load(filename); wearing.append((name,rv,rf,False,material))
    wearing_report=e.archive(P/'Front_Simple_Wearing.3mf',wearing,'Simple front | fit reference')
    report={'print':print_report,'wearing':wearing_report,'rotation_about_wearing_x_deg':135,
            'rotation':rotation.tolist(),'translation':translation.tolist(),
            'print_bounds_mm':[posed.min(0).tolist(),posed.max(0).tolist()],
            'settings_source':str(source.relative_to(ROOT)).replace('\\','/'),
            'settings_changes':{},
            'source_body_sha256':e.sha(G/'front_body.npz')}
    (P/'checks/export.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report,indent=2),flush=True)


if __name__=='__main__':main()
