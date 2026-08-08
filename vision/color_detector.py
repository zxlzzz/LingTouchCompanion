"""
color_detector — 专项颜色识别通道，给"已知障碍物只有长条气球+椅子"这种
封闭场景兜底远距离检测。

深度估计在远距离时信号会弱到被噪声淹没（实测约 2m 开外基本测不出来），
但颜色不会——只要气球本身饱和度够、色相跟场景里其它东西不重叠，哪怕在
画面里只剩几个像素，饱和度+色相判断依然成立，比深度能测得远得多。

跟 grid_mapper.py 的深度管线是"叠加"关系（OR），不是替换：颜色通道负责
兜底"深度信号太弱但其实有东西"的情况，深度通道继续负责一般性的障碍物
安全检测（比如万一场景里出现别的东西）。

已用 calibrate_balloon_color.py 对实物气球标定过（2026-08-08，8 个取样点，
实际是黄色，不是最早猜的紫色）。还没跟椅子的颜色交叉核对过是否重叠——
如果后续发现椅子也会触发这个通道，把椅子也过一遍 calibrate_balloon_color.py，
拿椅子的 H 范围跟下面的 BALLOON_HUE_RANGE 比一下有没有交集。
"""
import numpy as np
import cv2

from config import GRID_COLS, GRID_ROWS, ROI_TOP_RATIO, ROI_BOTTOM_RATIO

# OpenCV HSV: H∈[0,179]（对应色相 0~358°），S/V∈[0,255]
# 实物标定结果：8 个取样点 H=26~28（色相约52~56°，黄偏橙），
# S=86~121，V=194~240（偏亮、有一定光泽）。calibrate_balloon_color.py
# 自动加了余量：H±5、S-15、V-15。
BALLOON_HUE_RANGE = (21, 33)
BALLOON_SAT_MIN = 71
BALLOON_VAL_MIN = 178

# 颜色信号不会像深度那样被"格子里大部分是背景像素"稀释——只要格子里有
# 这么多个像素命中颜色范围就算数，可以给得比深度那边的统计门槛低很多，
# 这也是它能测得比深度远的原因之一。
BALLOON_MIN_PIXELS_PER_CELL = 3


def color_mask(frame_bgr, hue_range=BALLOON_HUE_RANGE,
                sat_min=BALLOON_SAT_MIN, val_min=BALLOON_VAL_MIN):
    """整张图上符合气球颜色的像素掩码（bool, 同 frame_bgr 的 H×W）。"""
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    hue, sat, val = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    lo, hi = hue_range
    return (hue >= lo) & (hue <= hi) & (sat >= sat_min) & (val >= val_min)


def detect_color_grid(
    frame_bgr,
    cols=GRID_COLS,
    rows=GRID_ROWS,
    roi_top=ROI_TOP_RATIO,
    roi_bottom=ROI_BOTTOM_RATIO,
    hue_range=BALLOON_HUE_RANGE,
    sat_min=BALLOON_SAT_MIN,
    val_min=BALLOON_VAL_MIN,
    min_pixels=BALLOON_MIN_PIXELS_PER_CELL,
):
    """按颜色把气球定位到 9x10 栅格。ROI 裁剪和分格方式跟
    grid_mapper.compute_obstacle_scores 保持一致，这样"行=远近"的编码
    含义不会因为换了检测通道就变——颜色通道不知道真实深度，但物体在画面
    里的垂直位置（近大远小的透视关系）跟深度通道用的是同一套假设。

    Returns:
        grid: (rows, cols) bool
    """
    h, w = frame_bgr.shape[:2]
    mask = color_mask(frame_bgr, hue_range, sat_min, val_min)

    y_start = int(h * roi_top)
    y_end = int(h * (1.0 - roi_bottom))
    roi_mask = mask[y_start:y_end, :]
    rh, rw = roi_mask.shape
    cell_h, cell_w = rh / rows, rw / cols

    grid = np.zeros((rows, cols), dtype=bool)
    for r in range(rows):
        y0, y1 = int(r * cell_h), int((r + 1) * cell_h)
        for c in range(cols):
            x0, x1 = int(c * cell_w), int((c + 1) * cell_w)
            if roi_mask[y0:y1, x0:x1].sum() >= min_pixels:
                grid[r, c] = True
    return grid
