"""Export both handle parts with all original project transforms and settings."""
import shutil
import xml.etree.ElementTree as ET
import zipfile
import numpy as np
from source import P, SOURCE, NS, PRODUCTION, read_source


def main():
    rows,members=read_source()
    changed={}
    for row in rows:
        with np.load(P/'geometry'/(row['name']+'.npz')) as q:
            v,f=q['v'],q['f']
        if np.array_equal(v,row['v']) and np.array_equal(f,row['f']):continue
        entry=row['model_entry']
        root=changed.setdefault(entry,ET.fromstring(members[entry]))
        obj=next(o for o in root.findall(NS+'resources/'+NS+'object') if o.get('id')==row['mesh_object_id'])
        mesh=obj.find(NS+'mesh');mesh.clear()
        vs=ET.SubElement(mesh,NS+'vertices');ts=ET.SubElement(mesh,NS+'triangles')
        for point in v:
            ET.SubElement(vs,NS+'vertex',**{k:format(float(n),'.17g') for k,n in zip('xyz',point)})
        for face in f:
            ET.SubElement(ts,NS+'triangle',**{k:str(int(n)) for k,n in zip(('v1','v2','v3'),face)})
        config=ET.fromstring(members['Metadata/model_settings.config'])
        settings=next(o for o in config.findall('object') if o.get('id')==row['build_object_id'])
        settings.find('metadata[@face_count]').set('face_count',str(len(f)))
        part=settings.find('part')
        part.find('mesh_stat').set('face_count',str(len(f)))
        members['Metadata/model_settings.config']=ET.tostring(config,encoding='UTF-8',xml_declaration=True)
    output=P/'Handle_Print.3mf'
    if not changed:
        shutil.copyfile(SOURCE,output)
    else:
        ET.register_namespace('',NS[1:-1]);ET.register_namespace('p',PRODUCTION[1:-1])
        for entry,root in changed.items():members[entry]=ET.tostring(root,encoding='UTF-8',xml_declaration=True)
        with zipfile.ZipFile(output,'w',compression=zipfile.ZIP_DEFLATED) as archive:
            for name,raw in members.items():archive.writestr(name,raw)
    back,unused=read_source(output,require_source_hash=False)
    for row in back:
        with np.load(P/'geometry'/(row['name']+'.npz')) as q:
            assert np.array_equal(q['v'],row['v']) and np.array_equal(q['f'],row['f'])
    print('Exported both handle parts with original print pose and metadata.',flush=True)


if __name__=='__main__':main()
