"""
export_sample — 抓一帧（本机摄像头 / 图片文件）跑一遍深度管线，把中间结果落盘。

排查"某类物体检测不对/受颜色影响"时不用干等预览窗口，直接把这一帧的
每一步中间结果存下来慢慢看：

  originals.jpg   原始画面
  depth_raw.npy   深度图原始数值（米），float32
  depth_heat.jpg  深度热力图（黄=远，紫黑=近）
  scores.npy      每格 obstacle score 原始值（未阈值化，见 grid_mapper.compute_obstacle_scores）
  scores_heat.jpg 每格 score 可视化热力图 + 数值标注（诊断颜色偏置的关键：
                   同一实际距离、不同颜色的物体，score 如果不一样，
                   说明模型确实把颜色/材质当成了深度线索）
  grid.jpg        最终 9x10 点阵（摄像头视角，未镜像，含深度+颜色两个通道叠加后的结果）
  color_mask.jpg  颜色专项通道命中的像素（白=命中），配合 calibrate_balloon_color.py 调阈值用
  meta.json       尺寸、激活数、耗时等元信息

用法:
    python export_sample.py --camera 0                    # 本机摄像头抓一帧
    python export_sample.py --camera 0 --model base --gpu  # 用 GPU + base 模型
    python export_sample.py --image path/to/xxx.jpg
    python export_sample.py --image a.jpg --tag black_box  # 加标签方便和其它样本对比
    python export_sample.py --image a.jpg --out-dir data/exports/mytest
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from depth_estimator import DepthEstimator
from grid_mapper import compute_obstacle_scores, depth_map_to_dot_frame
from color_detector import color_mask
from config import GRID_COLS, GRID_ROWS, FRAME_LEN, ROI_TOP_RATIO, ROI_BOTTOM_RATIO


def depth_to_heatmap(depth_map):
    d = depth_map.copy()
    d_min, d_max = d.min(), d.max()
    if d_max - d_min > 1e-6:
        d = (d - d_min) / (d_max - d_min)
    else:
        d = np.zeros_like(d)
    d = (d * 255).astype(np.uint8)
    return cv2.applyColorMap(d, cv2.COLORMAP_INFERNO)


def scores_to_heatmap(scores, cell_px=48):
    """把 (rows, cols) 的 score 矩阵画成带数值标注的热力图，蓝=低分，红=高分。"""
    rows, cols = scores.shape
    lo, hi = float(scores.min()), float(scores.max())
    rng = max(hi - lo, 1e-6)
    norm = ((scores - lo) / rng * 255).astype(np.uint8)
    big = cv2.resize(norm, (cols * cell_px, rows * cell_px), interpolation=cv2.INTER_NEAREST)
    heat = cv2.applyColorMap(big, cv2.COLORMAP_JET)
    for r in range(rows):
        for c in range(cols):
            x, y = c * cell_px + 4, r * cell_px + cell_px // 2
            cv2.putText(heat, f"{scores[r, c]:+.2f}", (x, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.32, (255, 255, 255), 1, cv2.LINE_AA)
            cv2.rectangle(heat, (c * cell_px, r * cell_px),
                          ((c + 1) * cell_px - 1, (r + 1) * cell_px - 1), (60, 60, 60), 1)
    return heat


def render_dot_grid(frame_flat, cell_size=24):
    h, w = GRID_ROWS * cell_size, GRID_COLS * cell_size
    img = np.zeros((h, w, 3), dtype=np.uint8)
    grid = frame_flat.reshape(GRID_ROWS, GRID_COLS)
    for r in range(GRID_ROWS):
        for c in range(GRID_COLS):
            y0, y1 = r * cell_size, (r + 1) * cell_size
            x0, x1 = c * cell_size, (c + 1) * cell_size
            color = (0, 220, 80) if grid[r, c] else (20, 25, 30)
            cv2.rectangle(img, (x0, y0), (x1 - 1, y1 - 1), color, -1)
    return img


def export_one(frame_bgr, estimator, out_dir: Path, tag=""):
    out_dir.mkdir(parents=True, exist_ok=True)
    prefix = f"{tag}_" if tag else ""

    h, w = frame_bgr.shape[:2]
    if w > 640:
        frame_bgr = cv2.resize(frame_bgr, (640, int(640 * h / w)))

    t0 = time.time()
    depth_map = estimator.estimate(frame_bgr)
    t_depth = time.time() - t0

    scores, baseline = compute_obstacle_scores(depth_map)
    frame = depth_map_to_dot_frame(depth_map, frame_bgr=frame_bgr)
    active = int(frame.sum())

    cv2.imwrite(str(out_dir / f"{prefix}original.jpg"), frame_bgr)
    np.save(out_dir / f"{prefix}depth_raw.npy", depth_map)
    cv2.imwrite(str(out_dir / f"{prefix}depth_heat.jpg"), depth_to_heatmap(depth_map))
    np.save(out_dir / f"{prefix}scores.npy", scores)
    cv2.imwrite(str(out_dir / f"{prefix}scores_heat.jpg"), scores_to_heatmap(scores))
    cv2.imwrite(str(out_dir / f"{prefix}grid.jpg"), render_dot_grid(frame))
    mask = color_mask(frame_bgr)
    cv2.imwrite(str(out_dir / f"{prefix}color_mask.jpg"), (mask.astype(np.uint8) * 255))

    meta = {
        "tag": tag,
        "shape": list(frame_bgr.shape),
        "depth_estimate_seconds": round(t_depth, 3),
        "active_dots": active,
        "total_dots": FRAME_LEN,
        "row_baseline_p25": [round(float(x), 4) for x in baseline],
        "score_min": round(float(scores.min()), 4),
        "score_max": round(float(scores.max()), 4),
        "roi_top_ratio": ROI_TOP_RATIO,
        "roi_bottom_ratio": ROI_BOTTOM_RATIO,
    }
    with open(out_dir / f"{prefix}meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)

    print(f"[export_sample] {tag or '(no tag)'}: {active}/{FRAME_LEN} active, "
          f"depth {t_depth*1000:.0f}ms, score range [{scores.min():+.2f}, {scores.max():+.2f}] "
          f"→ {out_dir}")
    return meta


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--camera", type=int, default=None, help="本机摄像头设备号")
    ap.add_argument("--image", type=str, default=None, help="处理已有图片")
    ap.add_argument("--model", choices=["small", "base", "large"], default="small")
    ap.add_argument("--gpu", action="store_true", help="用 GPU（需要装了 CUDA 版 torch）")
    ap.add_argument("--tag", default="", help="样本标签，用于文件名前缀和多样本对比")
    ap.add_argument("--out-dir", default=None, help="输出目录，默认 data/exports/<时间戳>")
    args = ap.parse_args()

    if args.camera is None and args.image is None:
        ap.error("需要 --camera 或 --image 其中之一")

    if args.image:
        frame = cv2.imread(args.image)
        if frame is None:
            print(f"无法读取图片: {args.image}")
            sys.exit(1)
    else:
        cap = cv2.VideoCapture(args.camera, cv2.CAP_DSHOW)
        if not cap.isOpened():
            print(f"无法打开摄像头 {args.camera}")
            sys.exit(1)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        # 前几帧丢弃，等自动曝光/对焦稳定
        for _ in range(5):
            cap.read()
        ret, frame = cap.read()
        cap.release()
        if not ret:
            print("读取摄像头帧失败")
            sys.exit(1)

    out_dir = Path(args.out_dir) if args.out_dir else \
        Path(__file__).parent / "data" / "exports" / time.strftime("%Y%m%d_%H%M%S")

    print(f"加载 {args.model} 模型 ({'GPU' if args.gpu else 'CPU'}) ...")
    estimator = DepthEstimator(model_size=args.model, use_gpu=args.gpu)
    estimator.load()

    export_one(frame, estimator, out_dir, tag=args.tag)


if __name__ == "__main__":
    main()
