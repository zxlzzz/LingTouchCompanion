from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
P=Path(__file__).resolve().parent
q=np.load(P/'medium_native.npz');v=q['v']
v=v[(v[:,0]>70)&(v[:,1]>-45)&(v[:,1]<45)&(v[:,2]>-35)&(v[:,2]<20)]
fig,ax=plt.subplots(figsize=(9,7),dpi=160)
p=ax.scatter(v[:,2],v[:,1],c=v[:,0],cmap='viridis',s=3,vmin=70,vmax=87)
ax.set_aspect('equal');ax.set_xlabel('native Z anterior');ax.set_ylabel('native Y superior');fig.colorbar(p,label='native X lateral')
ax.grid();fig.savefig(P/'ear_region_native.png')
print('ear image saved')
