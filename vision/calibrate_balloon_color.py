"""
calibrate_balloon_color — 拿实物气球对着摄像头，鼠标点几下，现场吸色，
算出应该填进 color_detector.py 的 HSV 阈值。

用法:
    python calibrate_balloon_color.py --camera 0
    python calibrate_balloon_color.py --image path/to/balloon.jpg

操作：
    左键点击气球上不同位置（建议点 5~10 下，覆盖高光/阴影/边缘不同亮度区域）
    按 R 重新取一帧（--camera 模式下）
    按 Q / ESC 结束，打印汇总结果和建议的阈值常量

原理：每次点击取一个 7x7 小块的 HSV 均值样本，最后把所有样本的
min/max 汇总成一个建议区间——顺便会打印"结果有没有跟典型灰墙灰地
（低饱和度背景）撞在一起"的提醒，避免调出来的范围太松导致背景误触发。
"""
import argparse
import sys
import os

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))

samples = []  # list of (h, s, v)
frame_bgr = None
window = "点气球取色 (Q/ESC 结束, R 重新取帧)"


def on_click(event, x, y, flags, param):
    if event != cv2.EVENT_LBUTTONDOWN:
        return
    hsv = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2HSV)
    h, w = hsv.shape[:2]
    x0, x1 = max(0, x - 3), min(w, x + 4)
    y0, y1 = max(0, y - 3), min(h, y + 4)
    patch = hsv[y0:y1, x0:x1].reshape(-1, 3)
    mean_h, mean_s, mean_v = patch.mean(axis=0)
    samples.append((float(mean_h), float(mean_s), float(mean_v)))
    print(f"  取样 #{len(samples)} @ ({x},{y}): H={mean_h:.0f} S={mean_s:.0f} V={mean_v:.0f}")
    cv2.circle(frame_bgr, (x, y), 4, (0, 255, 0), 1)
    cv2.imshow(window, frame_bgr)


def summarize():
    if not samples:
        print("没有取到任何样本。")
        return
    arr = np.array(samples)
    h_min, h_max = arr[:, 0].min(), arr[:, 0].max()
    s_min, s_max = arr[:, 1].min(), arr[:, 1].max()
    v_min, v_max = arr[:, 2].min(), arr[:, 2].max()

    # 稍微留点余量，避免刚好卡在边界外
    h_lo = max(0, h_min - 5)
    h_hi = min(179, h_max + 5)
    s_lo = max(0, s_min - 15)
    v_lo = max(0, v_min - 15)

    print(f"\n共 {len(samples)} 个样本")
    print(f"H 范围: {h_min:.0f} ~ {h_max:.0f}")
    print(f"S 范围: {s_min:.0f} ~ {s_max:.0f}")
    print(f"V 范围: {v_min:.0f} ~ {v_max:.0f}")

    if s_lo < 60:
        print("⚠️  饱和度偏低（<60），跟灰墙/灰地这类低饱和背景的区分度可能不够，"
              "建议换个光线更好、或者本身更鲜艳的气球，否则容易背景误触发。")

    print("\n把下面这几行贴进 vision/color_detector.py:")
    print(f"BALLOON_HUE_RANGE = ({int(h_lo)}, {int(h_hi)})")
    print(f"BALLOON_SAT_MIN = {int(s_lo)}")
    print(f"BALLOON_VAL_MIN = {int(v_lo)}")


def main():
    global frame_bgr
    ap = argparse.ArgumentParser()
    ap.add_argument("--camera", type=int, default=None)
    ap.add_argument("--image", type=str, default=None)
    args = ap.parse_args()

    if args.camera is None and args.image is None:
        ap.error("需要 --camera 或 --image 其中之一")

    cap = None
    if args.image:
        frame_bgr = cv2.imread(args.image)
        if frame_bgr is None:
            print(f"无法读取图片: {args.image}")
            sys.exit(1)
    else:
        cap = cv2.VideoCapture(args.camera, cv2.CAP_DSHOW)
        if not cap.isOpened():
            print(f"无法打开摄像头 {args.camera}")
            sys.exit(1)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        for _ in range(5):
            cap.read()
        ret, frame_bgr = cap.read()
        if not ret:
            print("读取摄像头帧失败")
            sys.exit(1)

    cv2.namedWindow(window)
    cv2.setMouseCallback(window, on_click)
    cv2.imshow(window, frame_bgr)
    print("左键点气球不同位置取色，R 重新取帧，Q/ESC 结束")

    while True:
        k = cv2.waitKey(30) & 0xFF
        if k in (ord('q'), 27):
            break
        if k == ord('r') and cap is not None:
            ret, new_frame = cap.read()
            if ret:
                frame_bgr = new_frame
                cv2.imshow(window, frame_bgr)
                print("已重新取帧")

    if cap is not None:
        cap.release()
    cv2.destroyAllWindows()
    summarize()


if __name__ == "__main__":
    main()
