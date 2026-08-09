"""
Phone camera -> PC metric depth (Depth-Anything-V2) -> topdown_pipeline -> BLE.

从 vision/phone_server.py 复制并改写扫描回调, 这份不 import vision/ 下任何文件
(两条路径完全独立, 见仓库根目录 tasks.md / README.md)。核心差异:

1. 深度估计换成 depth_runner.DepthRunner(Depth-Anything-V2 metric_depth, 输出真实米制
   深度), 不是 vision/depth_estimator.py 那个相对深度模型。
2. 栅格生成换成 topdown_pipeline.depth_to_grid()(俯视地面拟合真实坐标), 不是
   grid_mapper.py 那套图像平面阈值法。
3. 架构从"持续跑深度推理, 按键只是从缓存里取一份现成的栅格"改成"按键才按需触发一次
   拍照+推理"——metric-hypersim-vitl 比 vision/ 用的 small/base 模型重得多, 没必要
   每帧都跑；而且 topdown_pipeline 的 fx=3260 标定是在 3072px 宽原生照片上做的, 手机
   浏览器只有按需拍一张原生分辨率照片才划算(每 300ms 传一张 3072x4096 图不现实)。
   具体协议见 phone_camera.html 的注释: 手机轮询 /poll 拿"当前请求编号", 编号变化就
   立刻拍一张原生分辨率照片 POST 到 /frame?gen=N。
4. 没有 vision/config.py 那份配置, GRID_ROWS/GRID_COLS 直接从 frame_converter 拿,
   FX/CAM_H_TRUE 是这份自己的标定值(和 TOPDOWN_VALIDATION.md 一致)。

用法:
  python visionss/phone_server.py                  # 连 BLE 设备(默认名 LingChu-Tactile)
  python visionss/phone_server.py --no-ble          # 不连设备, 只能用控制台回车手动触发预览
  python visionss/phone_server.py --ble-device XXX  # 换设备名

不管连不连 BLE, 控制台按回车都会手动触发一次"拍照->深度推理->俯视栅格"并打印 ASCII
预览(连了 BLE 的话同时会真的下发到设备)——这是 --no-ble 模式下唯一的触发方式, 也是
调试 BLE 硬件时不用真的按板子上物理按键就能测一遍全流程的手段。
"""
import argparse
import json
import os
import ssl
import sys
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from socketserver import ThreadingMixIn
from urllib.parse import urlparse, parse_qs

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from depth_runner import DepthRunner
from topdown_pipeline import depth_to_grid, CAM_H_TRUE
from frame_converter import (GRID_ROWS, GRID_COLS, grid_to_bytes, bytes_to_grid,
                              ascii_preview, mirror_grid_horizontal)
from scan_link import ScanLink

# ── 标定参数(与 TOPDOWN_VALIDATION.md / 根目录 CLAUDE.md 一致) ──────────
FX = 3260.0             # 门宽复测标定值, 在 3072px 宽原生照片上量出来的
FX_BASE_WIDTH = 3072    # fx 对应的图像宽度——手机拍照分辨率必须匹配这个值, 不做运行时缩放
CAPTURE_TIMEOUT_S = 6.0  # 请求拍照后最多等这么久(手机对焦+编码+上传), 超时判定这次扫描失败
# ──────────────────────────────────────────────────────────────────────

PHONE_HTML = Path(__file__).parent / "phone_camera.html"
EXPORT_DIR = Path(__file__).parent / "data" / "exports"

state_lock = threading.Lock()
capture_gen = 0          # 单调递增的"拍照请求编号", /poll 把当前值告诉手机
awaiting_gen = None      # capture_and_infer() 当前在等哪个编号的照片(None = 没人在等)
pending_frame = None     # 收到的原生分辨率 BGR 帧, 交接给 capture_and_infer()
pending_event = threading.Event()
capture_serialize_lock = threading.Lock()  # 防止 BLE 按键和控制台回车并发触发时互相踩

runner = DepthRunner()
link = None  # 全局 ScanLink 实例, main() 里视 --no-ble 决定是否创建


def _request_capture():
    global capture_gen, awaiting_gen
    with state_lock:
        capture_gen += 1
        awaiting_gen = capture_gen
        my_gen = capture_gen
        pending_event.clear()
    return my_gen


def depth_to_heatmap(depth_map):
    d = depth_map.copy()
    d_min, d_max = float(d.min()), float(d.max())
    if d_max > d_min + 1e-6:
        d = (d - d_min) / (d_max - d_min)
    else:
        d = np.zeros_like(d)
    d = (d * 255).astype(np.uint8)
    return cv2.applyColorMap(d, cv2.COLORMAP_INFERNO)


def render_grid_image(grid, cell_size=32):
    g = np.asarray(grid).reshape(GRID_ROWS, GRID_COLS)
    h, w = GRID_ROWS * cell_size, GRID_COLS * cell_size
    img = np.zeros((h, w, 3), dtype=np.uint8)
    for r in range(GRID_ROWS):
        for c in range(GRID_COLS):
            y0, y1 = r * cell_size, (r + 1) * cell_size
            x0, x1 = c * cell_size, (c + 1) * cell_size
            color = (0, 220, 80) if g[r, c] else (20, 25, 30)
            cv2.rectangle(img, (x0, y0), (x1 - 1, y1 - 1), color, -1)
    return img


def export_debug(frame, depth, grid):
    """存一份原图/深度热力图/栅格图到 data/exports/, 方便离线复查每次扫描的中间结果
    (--no-ble 手动测试、真机联调排查漏检/误检都靠这个, 不依赖当时有没有开着预览窗口)。"""
    out_dir = EXPORT_DIR / time.strftime('%Y%m%d_%H%M%S')
    out_dir.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_dir / "original.jpg"), frame)
    np.save(out_dir / "depth_raw.npy", depth)
    cv2.imwrite(str(out_dir / "depth_heat.jpg"), depth_to_heatmap(depth))
    cv2.imwrite(str(out_dir / "grid.jpg"), render_grid_image(grid))
    meta = {"active_dots": int(np.asarray(grid).sum()), "total_dots": GRID_ROWS * GRID_COLS,
            "fx": FX, "cam_h_true": CAM_H_TRUE}
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_dir


def capture_and_infer():
    """frame_source 回调, 供 ScanLink 在收到 BLE 扫描请求(0x04)时调用, 也可以在控制台
    手动调用做 dry-run。请求手机拍一张原生分辨率照片 -> metric 深度推理 ->
    topdown_pipeline 俯视栅格 -> 设备穿戴镜像。超时/没收到有效照片返回 None。
    """
    with capture_serialize_lock:
        t0 = time.time()
        my_gen = _request_capture()
        got = pending_event.wait(timeout=CAPTURE_TIMEOUT_S)
        t1 = time.time()

        global pending_frame, awaiting_gen
        with state_lock:
            frame = pending_frame
            pending_frame = None
            awaiting_gen = None

        if not got or frame is None:
            print(f"[capture] gen={my_gen} 超时{CAPTURE_TIMEOUT_S}s 未收到手机拍照 "
                  f"(检查手机是否已打开 phone_camera.html 并点了'开始预览', 是否同一WiFi)")
            return None

        h, w = frame.shape[:2]
        if abs(w - FX_BASE_WIDTH) > 200:
            print(f"[capture] 警告: 收到照片宽={w}px, 和标定宽度{FX_BASE_WIDTH}px 偏差较大, "
                  f"fx={FX} 可能不准——这里不会自动按比例缩放 fx, 出现这条警告说明手机实际拍照"
                  f"分辨率跟标定值对不上, 需要人工检查(通常是 getUserMedia 的 ideal 分辨率被"
                  f"设备/浏览器降级了)")

        t2 = time.time()
        depth = runner.infer(frame)
        t3 = time.time()
        grid = depth_to_grid(depth, fx=FX, cam_h_true=CAM_H_TRUE)
        grid = mirror_grid_horizontal(grid)
        t4 = time.time()

        active = int(grid.sum())
        print(f"[capture] gen={my_gen} {w}x{h} | 拍照上传{t1-t0:.2f}s 深度推理{t3-t2:.2f}s "
              f"俯视栅格{t4-t3:.2f}s | 端到端{t4-t0:.2f}s | 激活{active}/{GRID_ROWS*GRID_COLS}")

        try:
            export_debug(frame, depth, grid)
        except Exception as e:
            print(f"[capture] 导出调试数据失败(不影响本次下发): {e!r}")

        return grid


class FrameHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # 静默 HTTP access log

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path in ('/', '/phone_camera.html'):
            if PHONE_HTML.exists():
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
                self.send_header('Pragma', 'no-cache')
                self.end_headers()
                self.wfile.write(PHONE_HTML.read_bytes())
            else:
                self.send_error(404)
        elif parsed.path == '/poll':
            with state_lock:
                gen = capture_gen
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"gen": gen}).encode())
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path.startswith('/frame'):
            qs = parse_qs(urlparse(self.path).query)
            try:
                gen = int(qs.get('gen', [''])[0])
            except (ValueError, IndexError):
                gen = None

            length = int(self.headers.get('Content-Length', 0))
            data = self.rfile.read(length)
            try:
                arr = np.frombuffer(data, np.uint8)
                frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            except Exception:
                frame = None

            accepted = False
            if frame is not None and gen is not None:
                global pending_frame
                with state_lock:
                    if gen == awaiting_gen:
                        pending_frame = frame
                        accepted = True
                        pending_event.set()
            # accepted=False 通常是"手机上传时这个 gen 已经不是电脑在等的那个了"
            # (超时后又晚到的上传、或者页面刚打开时的第一帧), 静默丢弃, 不当错误处理。

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            self.wfile.write(json.dumps({"accepted": accepted}).encode())
        else:
            self.send_error(404)


def get_ip():
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(('8.8.8.8', 80))
        return s.getsockname()[0]
    except Exception:
        return '127.0.0.1'
    finally:
        s.close()


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def ensure_cert():
    """自动生成自签名证书(和 vision/ 版逻辑一致, 但独立存一份在 visionss/ 目录下,
    不复用 vision/cert.pem——两条路径完全解耦)。"""
    cert_dir = Path(__file__).parent
    cert_file = cert_dir / 'cert.pem'
    key_file = cert_dir / 'key.pem'
    if cert_file.exists() and key_file.exists():
        return str(cert_file), str(key_file)

    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    import datetime

    key = rsa.generate_private_key(65537, 2048)
    key_file.write_bytes(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    ))

    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, 'LingTouch')])
    cert = x509.CertificateBuilder().subject_name(
        subject).issuer_name(subject).public_key(
        key.public_key()).serial_number(
        x509.random_serial_number()).not_valid_before(
        datetime.datetime.now(datetime.timezone.utc)
    ).not_valid_after(
        datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=3650)
    ).add_extension(x509.SubjectAlternativeName([
        x509.DNSName('localhost')
    ]), critical=False).sign(key, hashes.SHA256())

    cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return str(cert_file), str(key_file)


def console_loop():
    print("\n控制台: 回车 = 手动触发一次[拍照->深度推理->俯视栅格](连了BLE会同时真实下发); "
          "输入 q 回车 = 退出\n")
    while True:
        try:
            cmd = input()
        except EOFError:
            break
        if cmd.strip().lower() == 'q':
            break
        grid = capture_and_infer()
        if grid is None:
            print("本次拍照失败/超时, 跳过\n")
            continue
        print(ascii_preview(grid))
        data = grid_to_bytes(grid)
        if link is not None:
            link.send_now(frame=grid)
            print("已手动下发到设备\n")
        else:
            print(f"(--no-ble 模式, 未下发; 15字节: {data.hex()})\n")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--ble-device', default='LingChu-Tactile', help='BLE 设备名')
    ap.add_argument('--no-ble', action='store_true', help='只测拍照->栅格全流程，不连设备')
    args = ap.parse_args()

    ip = get_ip()
    cert, key = ensure_cert()

    print("[phone_server] 加载 Depth-Anything-V2 metric 模型 ...")
    runner.load()  # 启动时就加载好, 不要等第一次扫描才扛这个延迟——那样第一次的
                    # 端到端延迟数字会被模型加载时间污染, 没法用来评估真实体验
    print("[phone_server] CUDA 预热中(第一次真实推理前跑一张假图, 触发 cudnn autotune)...")
    _t0 = time.time()
    runner.infer(np.zeros((FX_BASE_WIDTH * 4 // 3, FX_BASE_WIDTH, 3), dtype=np.uint8))
    print(f"[phone_server] 预热完成 {time.time()-_t0:.1f}s "
          f"(实测: 预热前单次推理~13s, 预热后降到~0.6-0.9s, 差距就是 cudnn 第一次调 kernel "
          f"的一次性开销——不预热的话这个延迟会摊在使用者第一次真实扫描上)")

    if not args.no_ble:
        link = ScanLink(capture_and_infer, device_name=args.ble_device)
        link.start()

    httpd = ThreadingHTTPServer(('0.0.0.0', 8760), FrameHandler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert, key)
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()

    print()
    print("╔════════════════════════════════════════╗")
    print("║   LingTouch visionss Phone Camera      ║")
    print("╠════════════════════════════════════════╣")
    print(f"║   手机浏览器打开:                         ║")
    print(f"║   https://{ip}:8760                    ║")
    print("║                                        ║")
    print("║   浏览器会提示不安全，点击 高级→继续访问   ║")
    print("║   手机和电脑同一 WiFi                    ║")
    print("╚════════════════════════════════════════╝")

    try:
        console_loop()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.shutdown()
        if link is not None:
            link.stop()
