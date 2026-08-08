"""
Phone camera → PC depth estimation → live preview.

PC runs this server. Phone opens the HTML page in browser.
Phone captures frames via getUserMedia, sends them as HTTP POST.
PC processes with Depth Anything and shows preview window.

HTTPS is required for camera access on non-localhost browsers.
A self-signed certificate (cert.pem / key.pem) is auto-generated on first run.
The phone browser will show a warning — just tap "Advanced" → "Proceed".
"""
import numpy as np
import cv2
import threading
import time
import sys
import os
import ssl
import json
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from pathlib import Path
from io import BytesIO

sys.path.insert(0, os.path.dirname(__file__))
from depth_estimator import DepthEstimator
from grid_mapper import depth_map_to_dot_frame, mirror_frame_horizontal, compute_obstacle_scores
from config import GRID_COLS, GRID_ROWS, FRAME_LEN, MIRROR_HORIZONTAL
from scan_link import ScanLink
from export_sample import scores_to_heatmap
from color_detector import color_mask

WINDOW_NAME = "LingTouch Preview | Original . Heatmap . 9x10 Grid"

latest_frame = None
latest_braille = None          # 最近一次 90 点栅格，供 [SCAN] 取用
latest_braille_ts = 0.0
BRAILLE_MAX_AGE_S = 1.5        # 超龄帧不下发，防止相机断流后按键拿到旧画面
frame_lock = threading.Lock()
running = True
fps_smooth = 0
last_active = 0


def depth_to_heatmap(depth_map):
    d = depth_map.copy()
    d_min, d_max = d.min(), d.max()
    if d_max > d_min + 1e-6:
        d = (d - d_min) / (d_max - d_min)
    else:
        d = np.zeros_like(d)
    d = (d * 255).astype(np.uint8)
    return cv2.applyColorMap(d, cv2.COLORMAP_INFERNO)


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


EXPORT_DIR = Path(__file__).parent / "data" / "exports"


def export_current(frame, depth_map, braille):
    """按 E 键时把这一帧的中间结果落盘，复用 export_sample.py 同一套可视化，
    专治"看热力图/点阵看不出为什么"——scores_heat.jpg 里有每格的具体分数。"""
    out_dir = EXPORT_DIR / f"live_{time.strftime('%Y%m%d_%H%M%S')}"
    out_dir.mkdir(parents=True, exist_ok=True)

    scores, baseline = compute_obstacle_scores(depth_map)

    cv2.imwrite(str(out_dir / "original.jpg"), frame)
    np.save(out_dir / "depth_raw.npy", depth_map)
    cv2.imwrite(str(out_dir / "depth_heat.jpg"), depth_to_heatmap(depth_map))
    np.save(out_dir / "scores.npy", scores)
    cv2.imwrite(str(out_dir / "scores_heat.jpg"), scores_to_heatmap(scores))
    cv2.imwrite(str(out_dir / "grid.jpg"), render_dot_grid(braille))
    cv2.imwrite(str(out_dir / "color_mask.jpg"), (color_mask(frame).astype(np.uint8) * 255))
    meta = {
        "active_dots": int(braille.sum()),
        "total_dots": FRAME_LEN,
        "row_baseline_p25": [round(float(x), 4) for x in baseline],
        "score_min": round(float(scores.min()), 4),
        "score_max": round(float(scores.max()), 4),
    }
    with open(out_dir / "meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print(f"[export] 已导出到 {out_dir}")
    return out_dir


def get_latest_braille():
    with frame_lock:
        if latest_braille is None:
            return None
        if time.time() - latest_braille_ts > BRAILLE_MAX_AGE_S:
            return None
        return latest_braille.copy()


def process_loop():
    global latest_frame, latest_braille, latest_braille_ts, running, fps_smooth, last_active

    print("Loading Depth Anything V2...")
    estimator = DepthEstimator(model_size="base", use_gpu=True)
    estimator.load()
    print("Model ready.")

    while running:
        with frame_lock:
            frame = latest_frame.copy() if latest_frame is not None else None
        if frame is None:
            time.sleep(0.05)
            continue

        t0 = time.time()
        h, w = frame.shape[:2]
        if w > 640:
            frame = cv2.resize(frame, (640, int(640 * h / w)))

        depth_map = estimator.estimate(frame)
        braille = depth_map_to_dot_frame(depth_map, frame_bgr=frame)  # 摄像头视角，给预览用
        last_active = int(braille.sum())
        with frame_lock:
            # 发给设备的那份才镜像；预览面板要和原画面/热力图方向一致
            latest_braille = mirror_frame_horizontal(braille) if MIRROR_HORIZONTAL else braille
            latest_braille_ts = time.time()

        heatmap = depth_to_heatmap(depth_map)
        dot_img = render_dot_grid(braille)
        dt = time.time() - t0
        fps_smooth = 0.9 * fps_smooth + 0.1 * (1.0 / max(dt, 0.001))

        target_h = max(frame.shape[0], heatmap.shape[0], dot_img.shape[0])

        def pad(img, target):
            if img.shape[0] == target:
                return img
            p = np.zeros((target, img.shape[1], 3), dtype=np.uint8)
            p[:img.shape[0], :] = img
            return p

        panel = np.hstack([pad(frame, target_h),
                           pad(heatmap, target_h),
                           pad(dot_img, target_h)])
        cv2.putText(panel, f"{last_active}/{FRAME_LEN} active | {fps_smooth:.1f} FPS",
                    (8, 16), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (200, 200, 200), 1)
        if panel.shape[0] > 900:
            s = 900 / panel.shape[0]
            panel = cv2.resize(panel, None, fx=s, fy=s)

        cv2.imshow(WINDOW_NAME, panel)
        k = cv2.waitKey(1) & 0xFF
        if k == ord('q') or cv2.getWindowProperty(WINDOW_NAME, cv2.WND_PROP_VISIBLE) < 1:
            running = False
            break
        if k == ord(' ') and link is not None:
            link.send_now()          # 无按键时用空格手动触发一次下发
        if k == ord('e'):
            export_current(frame, depth_map, braille)  # 导出这一帧的原图/深度/逐格分数

    cv2.destroyAllWindows()


class FrameHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # suppress verbose HTTP logs

    def do_GET(self):
        if self.path == '/phone_camera.html' or self.path == '/':
            html_path = Path(__file__).parent / 'phone_camera.html'
            if html_path.exists():
                self.send_response(200)
                self.send_header('Content-Type', 'text/html; charset=utf-8')
                self.send_header('Cache-Control', 'no-store, no-cache, must-revalidate')
                self.send_header('Pragma', 'no-cache')
                self.end_headers()
                self.wfile.write(html_path.read_bytes())
            else:
                self.send_error(404)
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path == '/frame':
            length = int(self.headers.get('Content-Length', 0))
            data = self.rfile.read(length)
            try:
                arr = np.frombuffer(data, np.uint8)
                frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                if frame is not None:
                    global latest_frame
                    with frame_lock:
                        latest_frame = frame
            except Exception:
                pass

            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Access-Control-Allow-Origin', '*')
            self.end_headers()
            resp = f'{{"active":{last_active}}}'.encode()
            self.wfile.write(resp)
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
    """Handle requests in separate threads."""
    daemon_threads = True


def ensure_cert():
    """Generate self-signed cert if missing."""
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


link = None

if __name__ == '__main__':
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument('--ble-device', default='LingChu-Tactile', help='BLE 设备名')
    ap.add_argument('--no-ble', action='store_true', help='只看预览，不连设备')
    args = ap.parse_args()

    ip = get_ip()
    cert, key = ensure_cert()

    if not args.no_ble:
        link = ScanLink(get_latest_braille, device_name=args.ble_device)
        link.start()

    # Start processing thread
    t = threading.Thread(target=process_loop, daemon=True)
    t.start()

    # Start HTTPS server
    httpd = ThreadingHTTPServer(('0.0.0.0', 8760), FrameHandler)
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert, key)
    httpd.socket = ctx.wrap_socket(httpd.socket, server_side=True)

    print()
    print("╔════════════════════════════════════════╗")
    print("║   LingTouch Phone Camera Server        ║")
    print("╠════════════════════════════════════════╣")
    print(f"║   手机浏览器打开:                         ║")
    print(f"║   https://{ip}:8760                    ║")
    print("║                                        ║")
    print("║   浏览器会提示不安全，点击 高级→继续访问   ║")
    print("║   手机和电脑同一 WiFi | 按 Q 退出        ║")
    print("║   按 E 导出当前帧（原图/深度/逐格分数）    ║")
    print("╚════════════════════════════════════════╝")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        running = False
        httpd.shutdown()
    finally:
        if link is not None:
            link.stop()