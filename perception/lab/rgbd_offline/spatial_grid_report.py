"""Offline nested-grid result viewer; preview thresholds never erase small detections."""
import json
import html


def write_gallery(output,records,summary):
    cards=''.join(f'''<article id="case-{i}"><h2>{html.escape(r.get('name',f'样例 {i+1:02d}'))}</h2>
<p>来源：{html.escape(str(r.get('scene_id') or r.get('source_kind','')))} · 地面：{html.escape(r['status'])}</p>
<a href="{asset}_panel.jpg"><img src="{asset}_panel.jpg"></a>
<div class="comparison"><div><h3>10cm 小格（白线：40cm 边界）</h3><img src="{asset}_10cm.png"></div>
<div><h3>每个 40cm 格的障碍小格数 / 16</h3><div class="grid" id="grid-{i}"></div><p id="stats-{i}"></p></div></div>
<p><a href="{asset}_dots.png">保存的计数点阵</a> · <a href="{asset}.json">原始小格/计数 JSON</a> · <a href="{asset}_noise_rejected.png">被剔除的像素</a></p></article>''' for i,r in enumerate(records) for asset in [r.get('asset_prefix',f"frame_{r.get('frame',i):02d}")])
    navigation='<p>场景跳转： '+' · '.join(f'<a href="#case-{i}">{html.escape(r.get("name",str(i+1)))}</a>' for i,r in enumerate(records))+'</p>'
    fit_count=summary.get('successful_ground_frames',sum(r.get('ground') is not None for r in records))
    status=f'<p>共 {len(records)} 个输入，地面拟合通过 {fit_count} 个，其余保留未知。该数量不是识别准确率。</p>'
    data=[{key:r[key] for key in ['coarse_obstacle_subcells','coarse_free_subcells','coarse_unknown_subcells','noise_rejected_pixels']} for r in records]
    data_json=json.dumps(data,default=lambda a:a.tolist(),separators=(',',':'))
    default=summary['nested_grid']['coarse_min_obstacle_subcells']
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>灵触 10cm 到 40cm 点阵</title>
<style>body{font-family:system-ui,"Microsoft YaHei";background:#09131f;color:#edf3fa;max-width:1400px;margin:auto;padding:24px}p{color:#adc0d3;line-height:1.8}a{color:#6bddd0}article,.controls{padding:22px;background:#101d2d;border-radius:16px;margin:24px 0}img{width:100%;height:auto;border-radius:10px}.comparison{display:grid;grid-template-columns:1fr 1fr;gap:24px}.grid{display:grid;grid-template-columns:repeat(9,1fr);gap:5px;margin-top:40px}.cell{aspect-ratio:1;border:1px solid #60758b;border-radius:50%;display:flex;align-items:center;justify-content:center;font-size:21px;font-weight:600}.small{border:3px solid #ffd16d;background:#302719;color:#ffd16d}.free{background:#205a49;color:#71dfbe}.unknown{background:#24364b;color:#9eb0c5}.controls{position:sticky;top:8px;z-index:2;border:1px solid #3a566b}input{width:260px;vertical-align:middle}h3{font-size:19px}@media(max-width:800px){.comparison{grid-template-columns:1fr}.cell{font-size:16px}.controls{position:static}}</style>
<h1>灵触 · 深度去噪 → 10cm 小格 → 40cm 计数点阵</h1>
<p>'''+html.escape(summary.get('description','同一合成室内场景的五帧。'))+'''</p>'''+status+navigation+'''
<p>先用邻域深度一致性剔除无支撑跳变点，再保留所有通过检查的障碍测量；不按连通区域面积删除小物体。10cm 地面/障碍/未知 → 每 4×4 小格统计一次。地面拟合失败的场景保留未知，不通过逐图改变参数美化结果。</p>
<div class="controls"><label>40cm 点亮预览阈值 K：<input type="range" id="threshold" min="1" max="16" value="'''+str(default)+'''"><strong id="value"></strong></label>
<p>数字 n 表示该格内有 n/16 个障碍小格，不是物体面积真值。橙色：n≥K；黄色圈：0&lt;n&lt;K，已发现的小障碍仍保留；绿色 ○：16 个小格都满足地面支持；灰色 ?：其余未知。K 只影响右侧交互预览，已保存图/JSON 使用记录的默认值。</p></div>'''+cards+'''<p><a href="summary.json">参数与运行记录</a></p><script>
const DATA='''+data_json+''';
function draw(){const k=Number(document.getElementById('threshold').value);document.getElementById('value').textContent=k+'/16';
DATA.forEach((frame,index)=>{const parent=document.getElementById('grid-'+index);parent.innerHTML='';let bright=0,small=0,free=0,unknown=0;
for(let r=0;r<6;r++)for(let c=0;c<9;c++){const n=frame.coarse_obstacle_subcells[r][c],f=frame.coarse_free_subcells[r][c],u=frame.coarse_unknown_subcells[r][c];let el=document.createElement('div');el.className='cell';
if(n>=k){bright++;el.textContent=n;el.style.background=`rgb(${Math.round(130+125*n/16)},${Math.round(75+65*n/16)},40)`}
else if(n>0){small++;el.classList.add('small');el.textContent=n}
else if(f===16){free++;el.classList.add('free');el.textContent='○'}
else{unknown++;el.classList.add('unknown');el.textContent='?'}
el.title=`第${r+1}行 第${c+1}列\n障碍 ${n}/16 · 地面支持 ${f}/16 · 未知 ${u}/16\n前向 ${(1+(5-r)*.4).toFixed(1)}–${(1+(6-r)*.4).toFixed(1)}m`;parent.append(el)}
document.getElementById('stats-'+index).textContent=`亮起 ${bright} 格 · 阈下小障碍 ${small} 格 · 地面支持 ${free} 格 · 未知 ${unknown} 格；深度一致性剔除 ${frame.noise_rejected_pixels} 像素。上远下近，每个圆点对应 40cm 格。`})}
document.getElementById('threshold').addEventListener('input',draw);draw();</script></html>'''
    (output/'index.html').write_text(page,encoding='utf-8')
