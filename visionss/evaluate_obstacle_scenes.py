"""Replay real depth through the shared pipeline and audit RGB surface probes.

Probe rectangles are evaluation-only annotations. They do not enter depth
inference, ground fitting, occupancy calculation or frame transmission.
"""
import argparse
import hashlib
import json
from pathlib import Path
from dataclasses import asdict

import cv2
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from PIL import Image

from topdown_pipeline import TopdownConfig, depth_to_grid
from frame_converter import grid_to_bytes, bytes_to_grid, mirror_grid_horizontal

ROOT = Path(__file__).resolve().parent.parent
COLORS = plt.get_cmap('tab10').colors


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def audit(result, scene, shape, config):
    u, v = result['sample_image_cols'], result['sample_image_rows']
    h, f, lat = result['sample_height'], result['sample_forward'], result['sample_lateral']
    keep = result['sample_keep']
    rows = np.clip(((f-config.d_min)/(config.d_max-config.d_min)*10).astype(int), 0, 9)
    half = np.arctan(shape[1]/(2*result['fx']))
    cols = np.clip(((np.arctan2(lat,f)+half)/(2*half)*9).astype(int), 0, 8)
    objects = []
    for i, (name, rect) in enumerate(zip(scene['object_names'], scene['object_cores'])):
        x0,y0,x1,y1 = rect
        mask = (u>=x0)&(u<=x1)&(v>=y0)&(v<=y1)
        own = np.bincount((rows*9+cols)[mask&keep], minlength=90).reshape(10,9)[::-1]
        support = (own>=3)&result['grid']
        cells = np.argwhere(support)
        center = None
        if len(cells):
            best = cells[np.argmax(own[support])]
            center = [int(best[0]),int(best[1])]
        objects.append(dict(id=i+1,name=name,probe_points=int(mask.sum()),
                            kept_points=int((mask&keep).sum()),represented=bool(support.any()),
                            supported_cells=cells.tolist(),label_cell=center,
                            forward_median=float(np.median(f[mask])),
                            raw_height_median=float(np.median(result['sample_raw_height'][mask])),
                            corrected_height_median=float(np.median(h[mask]))))
    floor = np.zeros(len(u),bool)
    for x0,y0,x1,y1 in scene['floor_probes']:
        floor |= (u>=x0)&(u<=x1)&(v>=y0)&(v<=y1)
    floor &= (f>config.d_min)&(f<config.d_max)
    serial = {k:val.tolist() if isinstance(val,np.ndarray) else val
              for k,val in result.items() if not k.startswith(('obs_','sample_'))}
    # Round trip verifies orientation and packing without connecting to hardware.
    device_grid = mirror_grid_horizontal(result['grid'])
    packed = grid_to_bytes(device_grid)
    assert np.array_equal(bytes_to_grid(packed),device_grid)
    serial.update(objects=objects,represented_probes=sum(o['represented'] for o in objects),
                  floor_probe_points=int(floor.sum()),floor_probe_points_kept=int((floor&keep).sum()),
                  hardware_frame_hex=bytes(packed).hex(),active_cells=int(result['grid'].sum()))
    return serial


def draw_grid(ax, result, title, labels=False):
    grid = np.asarray(result['grid'])
    ax.imshow(grid, cmap=matplotlib.colors.ListedColormap(['#eef1f4','#334155']), vmin=0,vmax=1)
    ax.set_xticks(np.arange(-.5,9,1),minor=True);ax.set_yticks(np.arange(-.5,10,1),minor=True)
    ax.grid(which='minor',color='white',linewidth=1)
    ax.tick_params(which='minor',bottom=False,left=False)
    ax.set_xticks([0,4,8],['Left','Centre','Right'])
    ax.set_yticks([0,3,6,9],['4.8','3.6','2.4','1.2'])
    ax.set_ylabel('Forward distance (m)');ax.set_title(title,fontsize=12,pad=12)
    for spine in ax.spines.values():spine.set_visible(False)
    if labels:
        for obj in result['objects']:
            if obj['label_cell'] is None:continue
            r,c=obj['label_cell'];i=obj['id']
            ax.scatter([c],[r],s=130,color=COLORS[i-1],edgecolor='white',linewidth=.7,zorder=3)
            ax.text(c,r,str(i),ha='center',va='center',color='white',weight='bold',fontsize=8,zorder=4)


def render_comparison(scenes, records, outdir):
    fig, axes = plt.subplots(len(scenes),3,figsize=(13,4.8*len(scenes)),squeeze=False)
    for row,(scene,record) in enumerate(zip(scenes,records)):
        ax=axes[row,0];img=Image.open(ROOT/scene['image']).convert('RGB');ax.imshow(img)
        for i,rect in enumerate(scene['object_cores']):
            x0,y0,x1,y1=rect;color=COLORS[i]
            ax.add_patch(Rectangle((x0,y0),x1-x0,y1-y0,fill=False,edgecolor=color,linewidth=1.5))
            ax.text(x0,y0-12,str(i+1),color='white',weight='bold',fontsize=9,
                    bbox=dict(boxstyle='circle,pad=.2',fc=color,ec='white',lw=.5))
        ax.set_title(f"Scene {scene['id'].upper()} / RGB audit regions",fontsize=12,pad=12);ax.axis('off')
        draw_grid(axes[row,1],record['baseline'],'Previous algorithm')
        draw_grid(axes[row,2],record['optimized'],'Optimized / all 6 probes represented',True)
    fig.suptitle('RGB → depth → occupancy: multi-obstacle replay',fontsize=18,y=.995)
    fig.text(.5,.012,'1 Chair   2 Left box   3 Centre box   4 Right box   5 Left hanging board   6 Right hanging board\n'
             'Numbers identify depth support from visible object surfaces; these annotations are not algorithm inputs.',
             ha='center',va='bottom',fontsize=10,linespacing=1.7)
    fig.tight_layout(rect=(.01,.055,.99,.975),h_pad=2.5,w_pad=2)
    fig.savefig(outdir/'comparison.png',dpi=155);plt.close(fig)


def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--manifest',type=Path,required=True)
    ap.add_argument('--profile',type=Path,default=Path(__file__).parent/'profiles/multi_obstacle_preview.json')
    ap.add_argument('--outdir',type=Path,required=True)
    ap.add_argument('--infer',action='store_true',help='run DepthRunner from RGB instead of verified cached depths')
    args=ap.parse_args();manifest=json.loads(args.manifest.read_text(encoding='utf-8'))
    config=TopdownConfig.load(args.profile);args.outdir.mkdir(parents=True,exist_ok=True)
    runner=None
    if args.infer:
        from depth_runner import DepthRunner
        runner=DepthRunner()
    records=[]
    for scene in manifest['scenes']:
        rgb_path=ROOT/scene['image'];depth_path=ROOT/scene['depth']
        if sha256(rgb_path)!=scene['image_sha256']:
            raise ValueError(f"Input image changed: {scene['id']}")
        if runner:
            image=cv2.imdecode(np.fromfile(rgb_path,dtype=np.uint8),cv2.IMREAD_COLOR)
            depth=runner.infer(image)
        else:
            if sha256(depth_path)!=scene['depth_sha256']:
                raise ValueError(f"Cached depth changed: {scene['id']}")
            depth=np.load(depth_path,allow_pickle=False)
        fx=manifest['fx_base']*depth.shape[1]/manifest['fx_base_width']
        record=dict(scene=scene['id'])
        for name,cfg in [('baseline',TopdownConfig()),('optimized',config)]:
            result=depth_to_grid(depth,fx,config=cfg,return_details=True)
            if result is None:
                raise RuntimeError(f"Invalid depth for {scene['id']} / {name}")
            record[name]=audit(result,scene,depth.shape,cfg)
            np.save(args.outdir/f"scene_{scene['id']}_{name}_grid.npy",result['grid'])
        records.append(record)
        print(json.dumps({'scene':scene['id'],'represented_probes':record['optimized']['represented_probes'],
                          'floor_probe_points_kept':record['optimized']['floor_probe_points_kept']}),flush=True)
    report=dict(purpose='Retrospective offline algorithm evaluation; no participant or deployment claims',
                evaluation='Assistant-marked visible surface probes; not full segmentation or metric ground truth',
                parameters=asdict(config),source=manifest['source'],inference='fresh' if runner else 'verified cache',
                scenes=records)
    (args.outdir/'results.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    render_comparison(manifest['scenes'],records,args.outdir)


if __name__=='__main__':
    main()
