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
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from pathlib import Path
from io import BytesIO

sys.path.insert(0, os.path.dirname(__file__))
from depth_estimator import DepthEstimator
from grid_mapper import depth_map_to_dot_frame
from config import GRID_COLS, GRID_ROWS, FRAME_LEN

latest_frame = None
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


def process_loop():
    global latest_frame, running, fps_smooth, last_active

    print("Loading Depth Anything V2...")
    estimator = DepthEstimator(model_size="small", use_gpu=False)
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
        braille = depth_map_to_dot_frame(depth_map)
        last_active = int(braille.sum())

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

        cv2.imshow("LingTouch Preview | Original . Heatmap . 9x10 Grid", panel)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            running = False
            break

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


if __name__ == '__main__':
    ip = get_ip()
    cert, key = ensure_cert()

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
    print("╚════════════════════════════════════════╝")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        running = False
        httpd.shutdown()
