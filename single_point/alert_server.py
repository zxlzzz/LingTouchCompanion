"""
single_point/alert_server — phone_server.py 的 alert 版, 对照条件用。

Phone camera -> PC metric depth (Depth-Anything-V2) -> alert_pipeline -> BLE。
与 visionss/phone_server.py 共用同一套拍照(phone_camera.html)、深度推理
(depth_runner.DepthRunner)、BLE 下发(scan_link.ScanLink)基础设施——这几份文件
不复制，直接 import visionss/ 下的。唯一不同的是"深度图怎么变成输出"这一步：
visionss 版做 10x9 俯视栅格(给方位)，这份只判断身前一个矩形区域有没有障碍物，
输出为单个模组(M11)整体凸起或不凸起，二选一，不给方位信息。见根目录 1.md。

用法:
  python alert_server.py                   # 连 BLE 设备(默认名 LingChu-Tactile)
  python alert_server.py --no-ble          # 不连设备, 只能用控制台回车手动触发预览
  python alert_server.py --ble-device XXX  # 换设备名

不管连不连 BLE, 控制台按回车都会手动触发一次"拍照->深度推理->单点告警"并打印结果
(连了 BLE 的话同时会真的下发到设备)。

端口 8761 (visionss/ 用 8760)，两个条件的服务可以同时开着方便切换调试，但正式跑
实验时同一时间只应该开一个，避免同时触发两次拍照抢同一部手机。
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

_VISIONSS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "visionss")
sys.path.insert(0, _VISIONSS_DIR)          # phone_camera.html、frame_converter、scan_link、depth_runner 全部复用这份
sys.path.insert(0, os.path.dirname(__file__))  # alert_pipeline 是这个目录自己的

from depth_runner import DepthRunner
from frame_converter import GRID_ROWS, GRID_COLS, grid_to_bytes
from scan_link import ScanLink
from alert_pipeline import depth_to_alert, CAM_H_TRUE

# ── 标定参数(与 visionss/phone_server.py 保持一致——同一台相机、同一次标定) ──
FX = 3260.0             # 门宽复测标定值, 在 3072px 宽原生照片上量出来的
FX_BASE_WIDTH = 3072    # fx 对应的图像宽度(Mate 50 Pro 主摄竖拍 3072x4096)
FX_BASE_AR = 3072 / 4096  # 标定时的长宽比。宽度可以等比例换算 fx, 长宽比变了就不能
CAPTURE_ROTATE = cv2.ROTATE_90_CLOCKWISE  # 横版帧转竖版的方向, 见 to_portrait()
CAPTURE_TIMEOUT_S = 6.0  # 请求拍照后最多等这么久(手机对焦+编码+上传), 超时判定这次扫描失败
# ──────────────────────────────────────────────────────────────────────

ALERT_MODULE = 10  # M11, 0-based index 10 -> modRow=3 modCol=1 (第4行中间列), 无死点
                    # (memory 确认 M9-M11 全 OK)。选中间列纯粹是"手掌中央能摸到"，
                    # 和它是不是"检测区域中心"无关——这个对照条件本来就不给方位信息。

PHONE_HTML = Path(_VISIONSS_DIR) / "phone_camera.html"   # 复用 visionss 那份，不重复维护
EXPORT_DIR = Path(__file__).parent / "data" / "exports"

state_lock = threading.Lock()
capture_gen = 0
awaiting_gen = None
pending_frame = None
pending_event = threading.Event()
capture_serialize_lock = threading.Lock()

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


def to_portrait(frame):
    """把手机传来的横版帧转正成竖版, 逻辑与 visionss/phone_server.py 完全一致
    (同一部手机、同一段 phone_camera.html，横版的原因见 visionss/README.md
    "手机摄像头是横版的"一节)。"""
    h, w = frame.shape[:2]
    if w > h:
        return cv2.rotate(frame, CAPTURE_ROTATE)
    return frame


def resolve_fx(w, h):
    """按实际收到的照片尺寸换算 fx, 与 visionss/phone_server.py 同一套逻辑。"""
    ar = w / h
    if abs(ar - FX_BASE_AR) > 0.03:
        print(f"[capture] 拒绝: 照片长宽比 {ar:.3f} 与标定时的 {FX_BASE_AR:.3f} 不符 "
              f"({w}x{h})。传感器裁切变了, fx 不能等比例换算, 需要在这个分辨率下重新"
              f"标定(拍已知宽度的门/柜, fx = 像素宽 × 距离 / 实际宽度)")
        return None
    fx_eff = FX * w / FX_BASE_WIDTH
    if abs(w - FX_BASE_WIDTH) > 50:
        print(f"[capture] 注意: 照片宽 {w}px ≠ 标定宽 {FX_BASE_WIDTH}px, "
              f"长宽比一致, fx 已等比例换算 {FX:.0f} -> {fx_eff:.0f}")
    return fx_eff


def alert_to_grid(obstacle):
    """bool -> (10,9) 栅格, 只有 M11 覆盖的 6 个格子被点亮或全灭。

    M11 (ALERT_MODULE=10): modRow = 10//3 = 3, modCol = 10%3 = 1
    -> 栅格行 6-7, 栅格列 3-5, 物理位置在 5行x3列 模组阵列的第4行中间列。
    不需要 mirror_grid_horizontal —— 中间列单点居中, 左右镜像后还是自己
    (与 visionss 的 10x9 栅格不同, 那个每一列都有方位含义, 必须镜像抵消佩戴朝向)。
    """
    grid = np.zeros((GRID_ROWS, GRID_COLS), dtype=np.uint8)
    if obstacle:
        r = (ALERT_MODULE // 3) * 2  # = 6
        c = (ALERT_MODULE % 3) * 3   # = 3
        grid[r:r + 2, c:c + 3] = 1
    return grid


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


def export_debug(frame, depth, grid, obstacle, count, threshold):
    """存一份原图/深度热力图/栅格图 + meta 到 data/exports/，方便离线复查每次扫描的
    中间结果。meta.json 额外标注 mode/obstacle/count/threshold，便于离线批量评估时
    和 visionss/ 的导出数据区分开、按条件分组统计。"""
    out_dir = EXPORT_DIR / time.strftime('%Y%m%d_%H%M%S')
    out_dir.mkdir(parents=True, exist_ok=True)
    cv2.imwrite(str(out_dir / "original.jpg"), frame)
    np.save(out_dir / "depth_raw.npy", depth)
    cv2.imwrite(str(out_dir / "depth_heat.jpg"), depth_to_heatmap(depth))
    cv2.imwrite(str(out_dir / "grid.jpg"), render_grid_image(grid))
    meta = {
        "mode": "single_point_alert",
        "obstacle": bool(obstacle),
        "count": int(count),
        "threshold": int(threshold),
        "fx": FX,
        "cam_h_true": CAM_H_TRUE,
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")
    return out_dir


def capture_and_infer():
    """frame_source 回调, 供 ScanLink 在收到 BLE 扫描请求(0x04)时调用, 也可以在控制台
    手动调用做 dry-run。请求手机拍一张原生分辨率照片 -> metric 深度推理 ->
    alert_pipeline 单点告警 -> 转成只点亮 M11 的栅格。超时/没收到有效照片/地面拟合
    失败返回 None(不下发)。"""
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

        frame = to_portrait(frame)
        h, w = frame.shape[:2]
        fx_eff = resolve_fx(w, h)
        if fx_eff is None:
            return None

        t2 = time.time()
        depth = runner.infer(frame)
        t3 = time.time()
        result = depth_to_alert(depth, fx=fx_eff, cam_h_true=CAM_H_TRUE)
        if result is None:
            print("[capture] 本帧地面拟合失败, 不下发(重新按一次)")
            return None
        obstacle, count, threshold = result
        grid = alert_to_grid(obstacle)
        t4 = time.time()

        print(f"[capture] gen={my_gen} {w}x{h} | 拍照上传{t1-t0:.2f}s 深度推理{t3-t2:.2f}s "
              f"告警判定{t4-t3:.2f}s | 端到端{t4-t0:.2f}s")
        print(f"[ALERT] {'障碍 ■' if obstacle else '通畅 □'}  (存活点数 {count} / 阈值 {threshold})")

        try:
            export_debug(frame, depth, grid, obstacle, count, threshold)
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
    """自动生成自签名证书, 独立存一份在 single_point/ 目录下(不复用 visionss/cert.pem,
    两个条件的服务应该能各自独立开关, 不互相依赖)。"""
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
    print("\n控制台: 回车 = 手动触发一次[拍照->深度推理->单点告警](连了BLE会同时真实下发); "
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
            print("本次拍照失败/超时/地面拟合失败, 跳过\n")
            continue
        data = grid_to_bytes(grid)
        if link is not None:
            link.send_now(frame=grid)
            print("已手动下发到设备\n")
        else:
            print(f"(--no-ble 模式, 未下发; 15字节: {data.hex()})\n")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--ble-device', default='LingChu-Tactile', help='BLE 设备名')
    ap.add_argument('--no-ble', action='store_true', help='只测拍照->告警全流程，不连设备')
    ap.add_argument('--fx', type=float, default=None,
                     help='覆盖标定焦距(px, 对应转正后的竖版宽度)，见 visionss/phone_server.py 同名参数说明')
    args = ap.parse_args()
    if args.fx:
        FX = args.fx
        print(f"[alert_server] fx 覆盖为 {FX:.0f}px (按转正后的竖版宽度 {FX_BASE_WIDTH}px 计)")

    ip = get_ip()
    cert, key = ensure_cert()

    print("[alert_server] 加载 Depth-Anything-V2 metric 模型 ...")
    runner.load()
    print("[alert_server] CUDA 预热中(第一次真实推理前跑一张假图, 触发 cudnn autotune)...")
    _t0 = time.time()
    runner.infer(np.zeros((FX_BASE_WIDTH * 4 // 3, FX_BASE_WIDTH, 3), dtype=np.uint8))
    print(f"[alert_server] 预热完成 {time.time()-_t0:.1f}s")

    if not args.no_ble:
        link = ScanLink(capture_and_infer, device_name=args.ble_device)
        link.start()

    httpd = ThreadingHTTPServer(('0.0.0.0', 8761), FrameHandler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert, key)
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    server_thread.start()

    print()
    print("╔════════════════════════════════════════╗")
    print("║   LingTouch single_point Alert (对照)   ║")
    print("╠════════════════════════════════════════╣")
    print(f"║   手机浏览器打开:                         ║")
    print(f"║   https://{ip}:8761                    ║")
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
