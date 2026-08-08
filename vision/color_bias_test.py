"""
color_bias_test — 用合成场景隔离"颜色"这一个变量，检查它是否影响深度估计。

做法：造一个固定的房间/走廊背景（地板+墙+透视网格线，给模型足够的
真实深度线索），在同一个像素位置、同一个大小放一个"障碍物"箱体，
只改它的颜色（白/灰/黑/红/蓝），其余像素完全不变。理想情况下同一个
障碍物在 5 种颜色下的 obstacle score、是否被判定为障碍、点阵激活数
应该几乎一样——如果差异很大，说明模型确实把颜色/亮度当成了深度线索
而不是几何本身。

跑完后用 export_sample.py 同一套导出逻辑把每个颜色的中间结果落盘，
并打印一张汇总表方便对比。

用法:
    python color_bias_test.py --model base --gpu
    python color_bias_test.py                      # 默认 small + CPU（慢但能跑）
"""
import argparse
import json
import sys
import os
import time
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from depth_estimator import DepthEstimator
from export_sample import export_one
from grid_mapper import compute_obstacle_scores
from config import ROI_TOP_RATIO, ROI_BOTTOM_RATIO, GRID_ROWS, GRID_COLS

W, H = 640, 480

# 障碍物在图上的区域：约占中下部，模拟 1.4m 高摄像头前方 ~2m 处一个 1m 高的箱子
OBS_X0, OBS_X1 = 260, 400
OBS_Y0, OBS_Y1 = 230, 340

COLORS = {
    "white": (235, 235, 235),
    "gray":  (128, 128, 128),
    "black": (25, 25, 25),
    "red":   (40, 40, 200),    # BGR
    "blue":  (200, 90, 40),
}


def make_scene(obstacle_bgr):
    """走廊透视背景 + 固定位置/大小的障碍箱体，只有颜色变化。"""
    img = np.zeros((H, W, 3), dtype=np.uint8)

    horizon = 200
    # 墙面（带轻微渐变，避免纯平色对模型太失真）
    for y in range(0, horizon):
        shade = 150 + int(40 * (y / horizon))
        img[y, :] = (shade - 10, shade, shade + 5)
    # 地板（透视渐变，越靠近底部越亮，给模型近大远小的线索）
    for y in range(horizon, H):
        t = (y - horizon) / (H - horizon)
        shade = 90 + int(120 * t)
        img[y, :] = (shade - 15, shade - 5, shade)

    # 透视网格线（消失点在画面中央地平线），强化"近大远小"的深度线索
    vp = (W // 2, horizon)
    for x in range(-4, 5):
        p1 = (W // 2 + x * 60, H)
        cv2.line(img, vp, p1, (60, 60, 60), 1, cv2.LINE_AA)
    for frac in (0.3, 0.55, 0.8):
        y = int(horizon + (H - horizon) * frac)
        cv2.line(img, (0, y), (W, y), (60, 60, 60), 1, cv2.LINE_AA)

    # 障碍箱体：正面 + 顶面（简单赋予立体感），阴影统一，只换主色
    r, g, b = obstacle_bgr
    top_color = (min(r + 25, 255), min(g + 25, 255), min(b + 25, 255))
    cv2.rectangle(img, (OBS_X0, OBS_Y0), (OBS_X1, OBS_Y1), obstacle_bgr, -1)
    top_h = 18
    pts = np.array([
        [OBS_X0, OBS_Y0], [OBS_X1, OBS_Y0],
        [OBS_X1 - 14, OBS_Y0 - top_h], [OBS_X0 - 14, OBS_Y0 - top_h],
    ])
    cv2.fillPoly(img, [pts], top_color)
    cv2.rectangle(img, (OBS_X0, OBS_Y0), (OBS_X1, OBS_Y1), (10, 10, 10), 1)
    # 投影阴影
    cv2.ellipse(img, (int((OBS_X0 + OBS_X1) / 2), OBS_Y1 + 6), (75, 10), 0, 0, 360, (40, 40, 40), -1)

    return img


def obstacle_region_rowcols():
    """把像素区域换算成 9x10 栅格里对应的 (row, col) 范围，用于取该区域的 score。"""
    y0 = int(H * ROI_TOP_RATIO)
    y1 = int(H * (1.0 - ROI_BOTTOM_RATIO))
    roi_h = y1 - y0
    cell_h = roi_h / GRID_ROWS
    cell_w = W / GRID_COLS

    r0 = max(0, int((OBS_Y0 - y0) / cell_h))
    r1 = min(GRID_ROWS, int((OBS_Y1 - y0) / cell_h) + 1)
    c0 = max(0, int(OBS_X0 / cell_w))
    c1 = min(GRID_COLS, int(OBS_X1 / cell_w) + 1)
    return r0, r1, c0, c1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", choices=["small", "base", "large"], default="small")
    ap.add_argument("--gpu", action="store_true")
    ap.add_argument("--out-dir", default=None)
    args = ap.parse_args()

    out_dir = Path(args.out_dir) if args.out_dir else \
        Path(__file__).parent / "data" / "exports" / f"color_bias_{time.strftime('%Y%m%d_%H%M%S')}"

    print(f"加载 {args.model} 模型 ({'GPU' if args.gpu else 'CPU'}) ...")
    estimator = DepthEstimator(model_size=args.model, use_gpu=args.gpu)
    estimator.load()

    r0, r1, c0, c1 = obstacle_region_rowcols()
    print(f"障碍物对应栅格区域: 行[{r0}:{r1}) 列[{c0}:{c1})")

    results = []
    for name, bgr in COLORS.items():
        scene = make_scene(bgr)
        meta = export_one(scene, estimator, out_dir, tag=name)

        depth_map = estimator.estimate(scene)
        scores, baseline = compute_obstacle_scores(depth_map)
        obs_scores = scores[r0:r1, c0:c1]

        results.append({
            "color": name,
            "bgr": bgr,
            "obs_score_mean": float(obs_scores.mean()),
            "obs_score_max": float(obs_scores.max()),
            "active_dots_total": meta["active_dots"],
        })

    print("\n=== 颜色偏置对比（同一几何位置/大小，只换颜色） ===")
    print(f"{'颜色':<8}{'BGR':<16}{'区域内平均score':<18}{'区域内最高score':<18}{'总激活点数'}")
    for r in results:
        print(f"{r['color']:<8}{str(r['bgr']):<16}{r['obs_score_mean']:<18.3f}"
              f"{r['obs_score_max']:<18.3f}{r['active_dots_total']}")

    means = [r["obs_score_mean"] for r in results]
    spread = max(means) - min(means)
    print(f"\n区域内平均 score 在 5 种颜色间的极差: {spread:.3f}")
    print("（这个极差如果和 OBSTACLE_MARGIN=0.60 这类判定阈值同量级甚至更大，"
          "说明颜色确实能把同一个物体从'检测到'翻成'检测不到'，反之则说明"
          "当前算法对颜色总体不敏感，问题可能在别处。）")

    with open(out_dir / "summary.json", "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\n完整结果已导出到: {out_dir}")


if __name__ == "__main__":
    main()
