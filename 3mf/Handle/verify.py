"""Verify complete handle recovery against every original mesh and ZIP member."""
import argparse
import hashlib
import json
import numpy as np
from source import P,SOURCE,ROOT_MODEL,read_source,apply
from build import inspect


def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--require-baseline',action='store_true')
    args=ap.parse_args()
    source,source_members=read_source()
    path=P/'Handle_Print.3mf'
    output,members=read_source(path,require_source_hash=False)
    report={'source_sha256':hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
            'output_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),
            'whole_archive_identical':SOURCE.read_bytes()==path.read_bytes(),'parts':[]}
    for original,row in zip(source,output):
        with np.load(P/'geometry'/(row['name']+'.npz')) as q:v,f=q['v'],q['f']
        with np.load(P/'geometry'/(row['name']+'_print.npz')) as q:pv,pf=q['v'],q['f']
        info=inspect(row['v'],row['f'])
        same_shape=row['v'].shape==original['v'].shape
        info.update(name=row['name'],native_vertices_identical=np.array_equal(row['v'],original['v']),
                    native_triangles_identical=np.array_equal(row['f'],original['f']),
                    max_vertex_difference_mm=float(np.abs(row['v']-original['v']).max()) if same_shape else None,
                    transforms_identical=all(np.array_equal(row[k],original[k]) for k in ['component_transform','build_transform']),
                    generated_mesh_matches_export=np.array_equal(v,row['v']) and np.array_equal(f,row['f']),
                    print_mesh_matches_export=np.array_equal(pv,apply(row['v'],row['native_to_print'])) and np.array_equal(pf,row['f']))
        report['parts'].append(info)
    mesh_entries={row['model_entry'] for row in source}
    protected=set(source_members)-mesh_entries-{'Metadata/model_settings.config'}
    report['project_transforms_settings_and_other_members_identical']=set(source_members)==set(members) and all(source_members[n]==members[n] for n in protected)
    report['all_original_members_identical']=set(source_members)==set(members) and all(source_members[n]==members[n] for n in source_members)
    report['baseline_reproduction_pass']=report['whole_archive_identical'] and report['all_original_members_identical'] and all(r['native_vertices_identical'] and r['native_triangles_identical'] and r['transforms_identical'] for r in report['parts'])
    report['pass']=bool(report['project_transforms_settings_and_other_members_identical'] and all(r['transforms_identical'] and r['generated_mesh_matches_export'] and r['print_mesh_matches_export'] for r in report['parts']) and (not args.require_baseline or report['baseline_reproduction_pass']))
    (P/'checks/reproduction.json').write_text(json.dumps(report,indent=2),encoding='utf8')
    print(json.dumps(report,indent=2),flush=True)
    assert report['pass'],'Handle recovery differs; inspect checks/reproduction.json'


if __name__=='__main__':main()
