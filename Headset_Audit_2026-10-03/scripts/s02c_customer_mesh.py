"""Step 2c: tessellate every part of CS30_customer.stp into one npz (part index per triangle)."""
import numpy as np
from s02_stp_probe import load, tessellate, children, bbox
from common import RAW, DATA
s = load(RAW / 'CS30_customer.stp')
Vs, Fs, P, n = [], [], [], 0
names = []
k = 0
for top in children(s):
    for c in children(top):
        try:
            V, F = tessellate(c, 0.02)
        except Exception as e:
            continue
        Vs.append(V); Fs.append(F + n); P.append(np.full(len(F), k)); n += len(V)
        names.append([round(x, 3) for x in bbox(c)]); k += 1
import json
np.savez_compressed('/tmp/claude-0/-home-user-LingTouchCompanion/a3d04089-c5dd-5567-a32c-b263c145e9d4/scratchpad/cs30_customer_mesh.npz', v=np.concatenate(Vs), f=np.concatenate(Fs), part=np.concatenate(P), bboxes=np.array(names))
print(k, n)
