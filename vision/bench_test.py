"""
bench_test — 不接视觉，直接把已知图案打到板子上。

目的：在引入深度估计的不确定性之前，先单独锁死
"frame_converter 的打包顺序" 与 "固件 posToChain 的物理位置" 是否一致。
这是整条链路里唯一无法靠肉眼从摄像头画面反推的环节。

用法：
    python bench_test.py --port COM5                # 交互菜单
    python bench_test.py --port COM5 --pattern L    # 直接发一个图案
    python bench_test.py --port COM5 --sweep        # 逐点扫描（90次）
    python bench_test.py --dry-run --pattern L      # 不连板子，只打印预期

固件需为含 [SCAN] 打印的版本；本脚本自身不等待 [SCAN]，主动推帧。
"""

import argparse
import sys
import time

import numpy as np

from frame_converter import (
    GRID_COLS, GRID_ROWS, grid_to_bytes, bytes_to_grid,
    ascii_preview, hex_preview,
)


def _blank():
    return np.zeros((GRID_ROWS, GRID_COLS), dtype=np.uint8)


def pat_corner():
    """仅栅格左上角一点。预期：M1 = 0x04，板上最远端最左侧单点。"""
    g = _blank()
    g[0, 0] = 1
    return g


def pat_L():
    """左侧竖线 + 最近端横线，构成 L。左右/远近颠倒时形状完全不同。"""
    g = _blank()
    g[:, 0] = 1
    g[GRID_ROWS - 1, :] = 1
    return g


def pat_near_bar():
    """最近两行全满。预期：M13/M14/M15 = 0x3F，其余为 0。"""
    g = _blank()
    g[GRID_ROWS - 2:, :] = 1
    return g


def pat_far_bar():
    """最远两行全满。预期：M1/M2/M3 = 0x3F。"""
    g = _blank()
    g[:2, :] = 1
    return g


def pat_left_col():
    """最左三列全满。预期：M1/M4/M7/M10/M13 = 0x3F。"""
    g = _blank()
    g[:, :3] = 1
    return g


def pat_center_blob():
    """正中 2×2 团块，模拟一个正前方障碍。"""
    g = _blank()
    g[6:8, 4:6] = 1
    return g


def pat_all():
    return np.ones((GRID_ROWS, GRID_COLS), dtype=np.uint8)


def pat_clear():
    return _blank()


PATTERNS = {
    "corner":   pat_corner,
    "L":        pat_L,
    "near":     pat_near_bar,
    "far":      pat_far_bar,
    "left":     pat_left_col,
    "center":   pat_center_blob,
    "all":      pat_all,
    "clear":    pat_clear,
}


class Link:
    """
    ESP32-S3 用原生 USB CDC，打开串口不会复位板子，rawMode 会跨脚本运行保留。
    而固件的 raw 模式没有退出转义符——进去之后所有字节都是帧数据。
    所以这里必须先探测板子当前处于哪个模式，否则 "raw on\n" 这 7 个字符
    会被当成帧数据吃掉，导致后续所有帧错位 15 字节。
    """

    def __init__(self, port, baud=115200, dry=False, auto_clear=True):
        self.dry = dry
        self.auto_clear = auto_clear
        self.ser = None
        if dry:
            return
        import serial
        self.ser = serial.Serial(port, baud, timeout=0.2)
        time.sleep(2.0)
        self.ser.reset_input_buffer()
        self._handshake()

    def _handshake(self):
        """确保板子处于 raw 模式，且帧边界对齐。"""
        self.ser.write(b"raw on\n")
        self.ser.flush()
        echo = self._read_for(1.2)
        if "raw" in echo:
            print("[握手] 板子原在命令模式，已进入 raw 模式")
        else:
            # 没有回显 = 板子本来就在 raw 模式，刚才那 7 个字符被当成帧数据了。
            # 补 8 字节凑满一帧强制对齐（会闪一次乱帧，随后被真帧覆盖）。
            self.ser.write(b"\x00" * 8)
            self.ser.flush()
            time.sleep(2.5)
            self._read_for(0.5)
            print("[握手] 板子原在 raw 模式，已重新对齐帧边界")

    def _read_for(self, seconds):
        buf = b""
        t_end = time.time() + seconds
        while time.time() < t_end:
            n = self.ser.in_waiting
            if n:
                buf += self.ser.read(n)
            else:
                time.sleep(0.05)
        txt = buf.decode("utf-8", "ignore")
        for line in txt.splitlines():
            if line.strip():
                print("   <", line.strip())
        return txt

    def _drain(self):
        self._read_for(0.1)

    def _write_frame(self, data, wait=2.5):
        self.ser.write(data)
        self.ser.flush()
        time.sleep(wait)
        self._drain()

    def send(self, grid):
        data = grid_to_bytes(grid)
        print(ascii_preview(grid))
        print()
        print(hex_preview(data))
        if self.dry:
            return
        # 先清屏：避免 prevData 残留导致固件报 "[跳过] 数据无变化"，
        # 也让 SMA 走一遍完整的 落下→抬起，手感更接近实际使用
        if self.auto_clear and any(data):
            self._write_frame(bytes(15), wait=2.0)
        self._write_frame(data)

    def close(self):
        if self.ser:
            try:
                self.ser.write(bytes(15))   # 清屏，保持在 raw 模式（下次靠握手自愈）
                self.ser.flush()
                time.sleep(0.3)
            except Exception:
                pass
            self.ser.close()


def run_sweep(link):
    """逐点扫描 90 个栅格点，每次只亮一个。用于定位任何单点错位。"""
    for i in range(GRID_ROWS * GRID_COLS):
        r, c = divmod(i, GRID_COLS)
        g = _blank()
        g[r, c] = 1
        d = grid_to_bytes(g)
        m = next(k for k in range(15) if d[k])
        bit = d[m].bit_length() - 1
        print(f"\n[{i+1}/90] 栅格(行{r},列{c})  ->  M{m+1} bit{bit} (0x{d[m]:02X})")
        link.send(g)
        if not link.dry:
            input("      对得上按回车，Ctrl-C 中止 > ")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", default=None, help="串口，如 COM5 或 /dev/ttyUSB0")
    ap.add_argument("--baud", type=int, default=115200)
    ap.add_argument("--pattern", choices=sorted(PATTERNS), default=None)
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--dry-run", action="store_true", help="不连板子，只打印预期结果")
    ap.add_argument("--no-clear", action="store_true", help="发图案前不先清屏")
    args = ap.parse_args()

    if not args.dry_run and not args.port:
        ap.error("需要 --port，或使用 --dry-run")

    link = Link(args.port, args.baud, dry=args.dry_run, auto_clear=not args.no_clear)
    try:
        if args.sweep:
            run_sweep(link)
        elif args.pattern:
            link.send(PATTERNS[args.pattern]())
        else:
            names = sorted(PATTERNS)
            while True:
                print("\n图案: " + "  ".join(f"{i+1}.{n}" for i, n in enumerate(names)))
                s = input("选择编号 (q退出) > ").strip()
                if s.lower() in ("q", "quit", ""):
                    break
                if s.isdigit() and 1 <= int(s) <= len(names):
                    link.send(PATTERNS[names[int(s) - 1]]())
    except KeyboardInterrupt:
        pass
    finally:
        link.close()


if __name__ == "__main__":
    main()