import bpy,json,numpy as np,sys
from pathlib import Path
from mathutils import Vector
from mathutils.bvhtree import BVHTree
D=Path(__file__).parent.parent/sys.argv[1];a=np.load(D/'working_meshes.npz');meta=json.load(open(D/'working_objects.json'));poses=json.load(open(D/'design_data.json',encoding='utf-8'))['poses']
report=json.load(open(D/'geometry_check.json'))
for n,m in report['component_shell_intersections']:
 if meta[n]['category']=='structure':n,m=m,n
 v1=a[n+'__v'];f1=a[n+'__f'];v2=a[m+'__v'];f2=a[m+'__f'];t1=BVHTree.FromPolygons([Vector(x) for x in v1],f1.tolist(),True);t2=BVHTree.FromPolygons([Vector(x) for x in v2],f2.tolist(),True)
 hits=t1.overlap(t2);pts=np.mean(v2[f2[[p[1] for p in hits]]],axis=1);inv=np.linalg.inv(np.array(poses[meta[n]['owner']]['matrix']));pts=pts@inv[:3,:3].T+inv[:3,3]
 print(n,m,'hits',len(hits),'local patch centers',np.round(pts.min(0),2),np.round(pts.max(0),2))
