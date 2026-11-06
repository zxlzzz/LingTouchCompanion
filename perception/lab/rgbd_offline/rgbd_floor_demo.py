"""Offline RGB-D -> pretrained floor proposals -> measured geometry -> tactile grid.

Inputs are supplied explicitly; no sample dataset is bundled with this module.
"""
import argparse
from dataclasses import asdict
import hashlib
import html
import json
import os
from pathlib import Path
import platform
import statistics
import threading
import time

ROOT = Path(__file__).resolve().parent
os.environ.update(HF_HUB_OFFLINE='1', TRANSFORMERS_OFFLINE='1', HF_HUB_DISABLE_TELEMETRY='1',
                  OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='4')
import numpy as np
from PIL import Image, ImageDraw, ImageFont
import psutil
import torch
from transformers import AutoImageProcessor, SegformerForSemanticSegmentation
from geometry import Intrinsics, Config, unproject, to_ground, build_grid
from spatial_grid import (DepthFilterParams, NestedGridParams, filter_depth_measurements,
                          build_nested_grid)


def load_floor_model(path):
    processor = AutoImageProcessor.from_pretrained(str(path), local_files_only=True)
    model = SegformerForSemanticSegmentation.from_pretrained(
        str(path), local_files_only=True, use_safetensors=True).to('cpu').eval()
    floor_ids = [int(key) for key, value in model.config.id2label.items()
                 if value.strip().lower() == 'floor']
    if not floor_ids:
        raise ValueError('Model configuration has no floor class')
    return processor, model, floor_ids


def infer_floor_prior(rgb, processor, model, floor_ids):
    with torch.inference_mode():
        inputs = processor(images=rgb, return_tensors='pt')
        outputs = model(**inputs)
        semantic = processor.post_process_semantic_segmentation(
            outputs, target_sizes=[(rgb.height, rgb.width)])[0].cpu().numpy()
    return np.isin(semantic, floor_ids)


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for part in iter(lambda: f.read(1024*1024), b''):
            h.update(part)
    return h.hexdigest()


def fit_plane(candidates, observed, seed=1):
    """Native-like gates, applied to model candidates and independently to all observations."""
    if len(candidates) < 500:
        return None, '候选点不足 500'
    rng = np.random.default_rng(seed)
    fitting = candidates[rng.choice(len(candidates), 8000, replace=False)] if len(candidates)>8000 else candidates
    best, best_count = None, 0
    for _ in range(200):
        a,b,c = fitting[rng.choice(len(fitting),3,replace=False)]
        n = np.cross(b-a,c-a)
        length = np.linalg.norm(n)
        if length < 1e-8:
            continue
        n /= length
        h = -np.dot(n,a)
        if h < 0:
            n,h = -n,-h
        if not (.4 <= h <= 2.2 and -n[1] >= np.cos(np.deg2rad(75))):
            continue
        residual = np.einsum('ij,j->i', fitting,n)+h
        inliers = np.abs(residual)<=.03
        count = int(inliers.sum())
        if count>best_count:
            best,best_count = inliers,count
    if best is None or best_count<500:
        return None,'没有满足高度/方向约束的地面'
    selection=fitting[best]
    center=selection.mean(axis=0)
    n=np.linalg.svd(selection-center,full_matrices=False)[2][-1]
    h=-float(n@center)
    if h<0:
        n,h=-n,-h
    if not (.4<=h<=2.2 and -n[1]>=np.cos(np.deg2rad(75))):
        return None,'精修平面方向/高度不合格'
    residual=np.einsum('ij,j->i',candidates,n)+h
    inliers=np.abs(residual)<=.03
    if int(inliers.sum())<500:
        return None,'精修平面支持不足'
    forward=np.array([0.,0.,1.])-n[2]*n
    length=np.linalg.norm(forward)
    if length<1e-5:
        return None,'地面前向退化'
    forward/=length
    span=float(np.ptp(candidates[inliers]@forward))
    if span<.6:
        return None,'地面前向覆盖不足 0.6m'
    below_fraction=float(np.mean((np.einsum('ij,j->i',observed,n)+h)<-.10))
    if below_fraction>.05:
        return None,'全图点云不支持该地面（下方点超过 5%）'
    return {'normal':n,'height_m':h,'forward':forward,'right':np.cross(forward,n),
            'inliers':int(inliers.sum()),'rms_m':float(np.sqrt(np.mean(residual[inliers]**2))),
            'forward_span_m':span,'below_fraction':below_fraction},'有效'


def geometry(depth, k, floor_prior, depth_params=DepthFilterParams(), grid_params=NestedGridParams()):
    quality=filter_depth_measurements(depth,depth_params)
    valid=quality['valid']
    xyz=unproject(np.where(valid,depth,0).astype(np.float32),k)
    sample_valid=valid[::4,::4]
    sample=xyz[::4,::4]
    observed=sample[sample_valid]
    prior=sample_valid & floor_prior[::4,::4]
    ground,reason=fit_plane(sample[prior],observed)
    source='segformer_floor'
    attempts=[{'source':source,'status':reason,'candidates':int(prior.sum())}]
    if ground is None:
        rows=np.arange(0,k.height,4)[:,None]
        candidates=sample[sample_valid & (rows>=k.height*.55)]
        ground,reason=fit_plane(candidates,observed)
        source='geometry_fallback'
        attempts.append({'source':source,'status':reason,'candidates':len(candidates)})
    nested=build_nested_grid(np.empty((0,3)),grid_params)
    obstacle=np.zeros(valid.shape,dtype=bool)
    floor=np.zeros_like(obstacle)
    in_grid=np.zeros_like(obstacle)
    if ground is not None:
        # Use every valid measured point for classification/grid, not only floor/model pixels.
        coordinates=to_ground(xyz[valid],ground)
        heights=coordinates[:,2]
        obstacle[valid]=(heights>=grid_params.height_min_m)&(heights<=grid_params.height_max_m)
        floor[valid]=np.abs(heights)<=grid_params.ground_tolerance_m
        in_grid[valid]=(coordinates[:,0]>=-1.8)&(coordinates[:,0]<1.8)&(coordinates[:,1]>=1)&(coordinates[:,1]<3.4)
        nested=build_nested_grid(coordinates,grid_params)
    return {**nested,'valid':valid,'raw_valid':quality['raw_valid'],
            'noise_rejected':quality['rejected'],'depth_neighbor_support':quality['consistent_neighbors'],
            'obstacle':obstacle,'floor':floor,'in_grid':in_grid,
            'ground':ground,'ground_source':source if ground is not None else None,
            'attempts':attempts,'status':reason}


def font(size):
    path=Path('C:/Windows/Fonts/msyh.ttc')
    return ImageFont.truetype(str(path),size) if path.exists() else ImageFont.load_default(size=size)


def dots_image(grid,counts=None):
    image=Image.new('RGB',(640,520),'#101d2d')
    d=ImageDraw.Draw(image)
    d.text((25,20),'9×6 空间点阵' if counts is None else '40cm 格 · 障碍小格计数',font=font(27),fill='#f1f5fa')
    d.text((25,62),'每格 0.4m · 随相机朝向 · 未做手柄镜像',font=font(15),fill='#a3b7cd')
    d.text((25,105),'前向距离区间（上远 / 下近）',font=font(14),fill='#a3b7cd')
    for r in range(6):
        for c in range(9):
            x,y=110+c*53,148+r*49
            state=int(grid[r,c])
            count=int(counts[r,c]) if counts is not None else None
            if state==1:
                color='#ffae62' if count is None else (int(130+125*count/16),int(75+65*count/16),40)
                d.ellipse((x-15,y-15,x+15,y+15),fill=color,outline='#ffd3a8',width=2)
                if count is not None:
                    d.text((x,y),str(count),font=font(14),anchor='mm',fill='white')
            elif count is not None and count>0:
                d.ellipse((x-15,y-15,x+15,y+15),outline='#ffd369',width=3)
                d.text((x,y),str(count),font=font(14),anchor='mm',fill='#ffd369')
            elif state==0:
                d.ellipse((x-7,y-7,x+7,y+7),outline='#61d9ba',width=2)
            else:
                d.ellipse((x-11,y-11,x+11,y+11),fill='#2b3c50',outline='#596e85',width=1)
                d.text((x-5,y-10),'?',font=font(14),fill='#a3b7cd')
    for r in range(6):
        low=1+(5-r)*.4
        d.text((12,139+r*49),f'{low:.1f}–{low+.4:.1f}m',font=font(12),fill='#a3b7cd')
    d.text((84,429),'左 −1.8m',font=font(16),fill='#a3b7cd',anchor='lt')
    d.text((322,429),'0',font=font(16),fill='#a3b7cd',anchor='mt')
    d.text((560,429),'右 +1.8m',font=font(16),fill='#a3b7cd',anchor='rt')
    d.text((25,471),'● 障碍    ○ 地面支持    ? 未知' if counts is None else '数字为障碍小格数 / 16；黄圈保留阈下小障碍',font=font(16),fill='#d5e0ec')
    d.text((25,499),'0–1m 未显示；凸点不表示物体填满整个格子',font=font(12),fill='#a3b7cd')
    return image


def fine_grid_image(states):
    image=Image.new('RGB',(800,640),'#101d2d')
    d=ImageDraw.Draw(image)
    d.text((25,20),'10cm 小格 → 每 4×4 小格组成一个 40cm 格',font=font(24),fill='#f1f5fa')
    d.text((25,61),'橙：有效障碍支持  绿：地面支持  灰：未知；白线为 40cm 边界',font=font(16),fill='#a3b7cd')
    colors={0:'#246d5c',1:'#f5a158',2:'#29394d'}
    for r in range(24):
        for c in range(36):
            x,y=90+c*18,110+r*18
            d.rectangle((x,y,x+17,y+17),fill=colors[int(states[r,c])],outline='#142131')
    for r in range(0,25,4):
        y=110+r*18
        d.line((90,y,738,y),fill='#c5d7e5',width=2)
        d.text((80,y),f'{3.4-r*.1:.1f}m',font=font(13),anchor='rm',fill='#a3b7cd')
    for c in range(0,37,4):
        x=90+c*18
        d.line((x,110,x,542),fill='#c5d7e5',width=2)
    d.text((90,567),'−1.8m',font=font(16),anchor='lt',fill='#a3b7cd')
    d.text((414,567),'0',font=font(16),anchor='mt',fill='#a3b7cd')
    d.text((738,567),'+1.8m',font=font(16),anchor='rt',fill='#a3b7cd')
    d.text((25,610),'小障碍由测量一致性保留；不按连通区域面积直接删除。',font=font(16),fill='#a3b7cd')
    return image


def make_panel(rgb,depth,geo,index,scene_name=None,source_label='合成室内样例'):
    import cv2
    valid=geo['valid']
    scale=np.clip((depth-.1)/4.9,0,1)
    color=cv2.applyColorMap(((1-np.nan_to_num(scale))*255).astype(np.uint8),cv2.COLORMAP_TURBO)[:,:,::-1].copy()
    color[~valid]=[22,30,40]
    overlay=np.asarray(rgb).copy()
    for mask,tint in [(geo['floor'],[45,210,170]),(geo['obstacle'],[255,130,50])]:
        overlay[mask]=(overlay[mask]*.45+np.array(tint)*.55).astype(np.uint8)
    overlay[~valid]=(overlay[~valid]*.3).astype(np.uint8)
    if 'noise_rejected' in geo:
        rejected=geo['noise_rejected']
        overlay[rejected]=(np.asarray(rgb)[rejected]*.3+np.array([230,75,220])*.7).astype(np.uint8)
    dots=dots_image(geo['grid'],geo.get('coarse_obstacle_subcells'))
    canvas=Image.new('RGB',(1400,1230),'#09131f')
    d=ImageDraw.Draw(canvas)
    heading=f'灵触 · RGB-D 到点阵  |  '+(scene_name if scene_name else f'第 {index+1:02d} 帧')
    d.text((30,20),heading,font=font(30),fill='#f4f7fb')
    d.text((30,66),f'CPU / 预训练地面候选 + 数值深度几何 / {source_label}',font=font(18),fill='#a3b7cd')
    images=[rgb,Image.fromarray(color),Image.fromarray(overlay),dots]
    titles=['01 RGB 输入','02 数据集深度 · 固定色标 0.1–5m','03 掩码 · 橙障碍 / 绿地面 / 紫色剔除','04 空间点阵 · 数字为障碍小格数/16']
    for im,title,(x,y) in zip(images,titles,[(30,110),(730,110),(30,635),(730,635)]):
        d.text((x,y),title,font=font(21),fill='#e8eef7')
        tile=im.copy()
        tile.thumbnail((640,480))
        canvas.paste(tile,(x,y+38))
    counts=[int((geo['grid']==s).sum()) for s in [1,0,2]]
    height=f"{geo['ground']['height_m']:.2f}m" if geo['ground'] is not None else '未知'
    d.text((30,1175),f'地面：{geo["status"]}  /  相机高度 {height}  /  障碍 {counts[0]}  地面支持 {counts[1]}  未知 {counts[2]}',font=font(18),fill='#a3b7cd')
    return canvas


def json_default(value):
    if isinstance(value,np.ndarray):
        return value.tolist()
    if isinstance(value,np.generic):
        return value.item()
    raise TypeError(type(value).__name__)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--model',type=Path,default=ROOT.parents[1]/'models/segformer-b0-ade')
    parser.add_argument('--output',type=Path,default=ROOT.parents[1]/'.build/vision/rgbd_floor')
    parser.add_argument('--threads',type=int,default=4)
    parser.add_argument('--coarse-min-subcells',type=int,default=1)
    parser.add_argument('--depth-absolute-tolerance',type=float,default=.02)
    parser.add_argument('--depth-relative-tolerance',type=float,default=.01)
    parser.add_argument('--min-depth-neighbors',type=int,default=1)
    args=parser.parse_args()
    if not 1<=args.coarse_min_subcells<=16 or not 0<=args.min_depth_neighbors<=8:
        parser.error('Coarse threshold must be 1..16 and depth neighbors 0..8')
    depth_params=DepthFilterParams(absolute_tolerance_m=args.depth_absolute_tolerance,
                                  relative_tolerance=args.depth_relative_tolerance,
                                  min_consistent_neighbors=args.min_depth_neighbors)
    grid_params=NestedGridParams(coarse_min_obstacle_subcells=args.coarse_min_subcells)
    for file in ['config.json','preprocessor_config.json','model.safetensors']:
        if not (args.model/file).is_file():
            parser.error(f'Missing local model asset: {file}')
    if args.output.exists():
        parser.error('Choose a new output folder')
    if (args.input/'manifest.json').exists():
        manifest=json.loads((args.input/'manifest.json').read_text(encoding='utf-8'))
        if manifest['depth_meaning']!='optical_z' or not manifest['registered_to_rgb']:
            parser.error('This pipeline requires optical-Z depth registered to RGB')
        k=Intrinsics(**manifest['intrinsics'])
        frames=manifest['frames']
    else:
        camera=json.loads((args.input/'camera_primesense.json').read_text())
        matrix=np.array(camera['intrinsic_matrix']).reshape((3,3),order='F')
        k=Intrinsics(camera['width'],camera['height'],matrix[0,0],matrix[1,1],matrix[0,2],matrix[1,2])
        pairs=[line.split() for line in (args.input/'rgbd.match').read_text().splitlines() if line.strip() and not line.startswith('#')]
        frames=[{'depth':d,'rgb':r,'source_kind':'synthetic_indoor_rgbd_sample'} for d,r in pairs]
        manifest={'name':'Open3D SampleRedwoodRGBDImages','depth_scale':1000,
                  'source_kind':'synthetic_indoor_rgbd_sample',
                  'description':'同一合成室内场景的五帧；用于软件流程验证。'}
    if not frames or not np.isfinite(manifest['depth_scale']) or manifest['depth_scale']<=0:
        parser.error('Invalid frame list or depth scale')
    torch.set_num_threads(args.threads)
    process=psutil.Process()
    peak=[process.memory_info().rss]
    stopped=threading.Event()
    def monitor():
        while not stopped.wait(.02):
            mem=process.memory_info()
            peak[0]=max(peak[0],mem.rss,getattr(mem,'peak_wset',0))
    watcher=threading.Thread(target=monitor,daemon=True)
    watcher.start()
    try:
        load_start=time.perf_counter()
        floor_model=load_floor_model(args.model)
        load_ms=(time.perf_counter()-load_start)*1000
        args.output.mkdir(parents=True)
        records=[]
        for i,frame in enumerate(frames):
            depth_path,rgb_path=frame['depth'],frame['rgb']
            if 'intrinsics' in frame:
                k=Intrinsics(**frame['intrinsics'])
            start=time.perf_counter()
            with Image.open(args.input/rgb_path) as f:
                rgb=f.convert('RGB')
            with Image.open(args.input/depth_path) as f:
                raw=np.asarray(f).copy()
            if raw.dtype!=np.uint16 or raw.shape!=(k.height,k.width) or rgb.size!=(k.width,k.height):
                raise ValueError('RGB-D types/shapes do not match the calibrated sample')
            depth=raw.astype(np.float32)/manifest['depth_scale']
            t=time.perf_counter()
            prior=infer_floor_prior(rgb,*floor_model)
            inference_ms=(time.perf_counter()-t)*1000
            t=time.perf_counter()
            geo=geometry(depth,k,prior,depth_params,grid_params)
            geometry_ms=(time.perf_counter()-t)*1000
            prefix=f'frame_{i:02d}'
            Image.fromarray(prior.astype(np.uint8)*255).save(args.output/f'{prefix}_floor_prior.png')
            for name in ['obstacle','floor','valid','in_grid','noise_rejected']:
                Image.fromarray(geo[name].astype(np.uint8)*255).save(args.output/f'{prefix}_{name}.png')
            dots_image(geo['grid'],geo['coarse_obstacle_subcells']).save(args.output/f'{prefix}_dots.png')
            fine_grid_image(geo['fine_grid']).save(args.output/f'{prefix}_10cm.png')
            source_kind=frame.get('source_kind',manifest.get('source_kind','dataset_rgbd'))
            default_label='真实室内 RGB-D / NYU' if source_kind=='real_nyu_registered_rgbd' else '合成室内样例'
            source_label=frame.get('source_label',manifest.get('source_label',default_label))
            make_panel(rgb,depth,geo,i,frame.get('display_name'),source_label).save(args.output/f'{prefix}_panel.jpg',quality=94)
            record={'frame':i,'name':frame.get('display_name',frame.get('name',f'样例 {i+1:02d}')),
                    'scene_id':frame.get('scene_id'),'source_rgb':rgb_path,'source_depth':depth_path,
                    'depth_scale':manifest['depth_scale'],'intrinsics':asdict(k),
                    'source_metadata':frame,'source_kind':source_kind,'status':geo['status'],'ground':geo['ground'],
                    'ground_source':geo['ground_source'],'attempts':geo['attempts'],'grid':geo['grid'],
                    'band_hits':geo['band_hits'],'floor_subblocks':geo['floor_subblocks'],
                    'fine_grid':geo['fine_grid'],'fine_obstacle_hits':geo['fine_obstacle_hits'],
                    'fine_ground_hits':geo['fine_ground_hits'],
                    'coarse_obstacle_subcells':geo['coarse_obstacle_subcells'],
                    'coarse_free_subcells':geo['coarse_free_subcells'],
                    'coarse_unknown_subcells':geo['coarse_unknown_subcells'],
                    'small_obstacle_present':geo['small_obstacle_present'],
                    'raw_valid_pixels':int(geo['raw_valid'].sum()),
                    'filtered_valid_pixels':int(geo['valid'].sum()),
                    'noise_rejected_pixels':int(geo['noise_rejected'].sum()),
                    'valid_fraction':float(geo['valid'].mean()),'floor_prior_pixels':int(prior.sum()),
                    'obstacle_pixels':int(geo['obstacle'].sum()),'in_grid_obstacle_pixels':int((geo['obstacle']&geo['in_grid']).sum()),
                    'inference_ms':inference_ms,'geometry_ms':geometry_ms,
                    'total_process_and_export_ms':(time.perf_counter()-start)*1000}
            (args.output/f'{prefix}.json').write_text(json.dumps(record,default=json_default,ensure_ascii=False,indent=2),encoding='utf-8')
            records.append(record)
            print(f'[{i+1}/{len(frames)}] {record["name"]} model={inference_ms:.0f}ms geometry={geometry_ms:.0f}ms floor={geo["ground_source"]} grid={geo["grid"].tolist()}',flush=True)
        times=[r['inference_ms']+r['geometry_ms'] for r in records]
        summary={'dataset':manifest['name'],'description':manifest.get('description',''),
                 'source_kind':manifest.get('source_kind','mixed_rgbd'),
                 'frames':len(records),'successful_ground_frames':sum(r['ground'] is not None for r in records),
                 'device':'cpu','threads':args.threads,'model':'nvidia/segformer-b0-finetuned-ade-512-512',
                 'model_files_sha256':{p.name:digest(p) for p in args.model.iterdir() if p.is_file()},
                 'intrinsics':asdict(k),'model_load_ms':load_ms,'first_model_geometry_ms':times[0],
                 'steady_model_geometry_p50_ms':statistics.median(times[1:]) if len(times)>1 else None,
                 'steady_model_geometry_p95_ms':float(np.percentile(times[1:],95)) if len(times)>1 else None,
                 'sampled_process_peak_ram_mib':peak[0]/1024**2,'python':platform.python_version(),
                 'torch':torch.__version__,'geometry':{'height_band_m':[.1,1.9],'ground_tolerance_m':.05,
                    'grid_x_m':[-1.8,1.8],'grid_y_m':[1,3.4],'ground_sample_stride':4,'ransac_iterations':200,
                    'grid_uses_all_valid_points':True},
                 'depth_filter':asdict(depth_params),'nested_grid':asdict(grid_params),
                 'total_noise_rejected_pixels':sum(r['noise_rejected_pixels'] for r in records),
                 'limits':['Dataset replay; not CS30 sensor validation or accuracy evaluation.',
                           'Process RAM is not whole-device RAM; times exclude image export and loading.',
                           'Unknown remains distinct; no hardware unknown policy was selected.',
                           'Demo port follows major native gates but is not a bitwise native implementation.',
                           'Neighbor-consistency filtering cannot identify every coherent artifact from one frame.',
                           '10cm states are evidence bins, not complete object footprint or calibrated risk probability.',
                           'Coarse preview threshold does not turn detected small obstacles into free cells.']}
        if 'input_metadata' in manifest:
            summary['input_metadata']=manifest['input_metadata']
        (args.output/'summary.json').write_text(json.dumps(summary,default=json_default,ensure_ascii=False,indent=2),encoding='utf-8')
        from spatial_grid_report import write_gallery
        write_gallery(args.output,records,summary)
        print(json.dumps(summary,default=json_default,ensure_ascii=False,indent=2))
    finally:
        stopped.set()
        watcher.join()


if __name__=='__main__':
    main()
