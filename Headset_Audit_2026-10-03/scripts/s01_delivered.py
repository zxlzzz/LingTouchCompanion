"""Step 1: parse delivered 3MFs with own reader; volume, bounds, closure, components."""
import json, sys
import numpy as np
from common import *

def describe(path):
    res = {}
    for name, (V, F) in read_3mf(path).items():
        ec = edge_check(F)
        lab, n = components(F, len(V))
        comp_vol = sorted([volume(V, F[lab == k]) for k in range(n)], key=abs, reverse=True)
        res[name] = {'vertices': len(V), 'triangles': len(F), 'volume_mm3': volume(V, F),
                     'bbox_min': V.min(0).tolist(), 'bbox_max': V.max(0).tolist(),
                     'extent': (V.max(0) - V.min(0)).tolist(), **ec,
                     'components': n, 'component_volumes_mm3': comp_vol[:10]}
    return res

if __name__ == '__main__':
    out = {}
    paths = sys.argv[1:] or [str(FRONT_3MF), str(REAR_3MF)]
    for p in paths:
        out[p] = describe(p)
    print(json.dumps(out, indent=1))
