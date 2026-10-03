"""Step 1b: compare a regenerated 3MF against the delivered one, object by object (own parser)."""
import sys, json
import numpy as np
from common import read_3mf, volume

def compare(a_path, b_path):
    A, B = read_3mf(a_path), read_3mf(b_path)
    out = {'objects_regenerated': list(A), 'objects_delivered': list(B), 'per_object': {}}
    for name in B:
        if name not in A:
            out['per_object'][name] = 'MISSING in regenerated'; continue
        (Va, Fa), (Vb, Fb) = A[name], B[name]
        same_shape = Va.shape == Vb.shape and Fa.shape == Fb.shape
        r = {'vertices': [len(Va), len(Vb)], 'triangles': [len(Fa), len(Fb)],
             'volume_mm3': [volume(Va, Fa), volume(Vb, Fb)],
             'bbox_regen': [Va.min(0).tolist(), Va.max(0).tolist()],
             'bbox_deliv': [Vb.min(0).tolist(), Vb.max(0).tolist()]}
        if same_shape:
            r['max_vertex_diff_mm'] = float(np.abs(Va - Vb).max())
            r['faces_identical'] = bool((Fa == Fb).all())
        out['per_object'][name] = r
    return out

if __name__ == '__main__':
    print(json.dumps(compare(sys.argv[1], sys.argv[2]), indent=1))
