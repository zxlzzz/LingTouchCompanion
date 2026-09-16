"""
depth_server — 本地 HTTP 服务：浏览器上传一张图片 -> Depth-Anything-V2 metric 深度推理
-> 返回深度热力图(PNG, base64) + 深度统计(min/max/median, 米)。

配合仓库根目录 depth_preview.html 使用：
  1. 启动: D:\\anaconda\\envs\\LING\\python.exe visionss\\depth_server.py
  2. 浏览器直接双击打开 depth_preview.html（file:// 协议也没问题，服务端已开 CORS）
  3. depth_preview.html 里选图 -> 点"生成深度热力图" -> fetch 到 http://127.0.0.1:8765/infer

和 phone_server.py 的区别：这个不碰 BLE、不碰 topdown_pipeline 俯视栅格、不落盘任何
调试文件——纯粹"上传一张图，看一眼 metric 深度热力图长什么样"，给人肉眼判断深度模型在
某张图上效果好不好，不是标定/验证管线的一部分。复用 depth_runner.DepthRunner 同一套
模型加载/推理代码，保证跟 visionss/ 其它工具看到的是同一个模型、同一条推理路径。

只监听 127.0.0.1（本机回环地址），不对局域网暴露——这是纯本地单机工具，没做任何鉴权，
不要改成监听 0.0.0.0。

用法:
  python visionss/depth_server.py                 # 默认端口 8765
  python visionss/depth_server.py --port 9000
  python visionss/depth_server.py --max-side 2048  # 长边超过这个值就先等比缩小再推理
                                                    # （纯粹为了控制耗时/显存，不影响相对
                                                    # 深度效果的观感；传 0 关闭缩放）
"""
import argparse
import base64
import json
import os
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))
from depth_runner import DepthRunner

MAX_UPLOAD_BYTES = 30 * 1024 * 1024  # 30MB，防止异常大文件把内存打爆

runner = DepthRunner()
infer_lock = threading.Lock()  # 单模型实例，同一时间只跑一次推理
MAX_SIDE = 2048  # 由 main() 按 --max-side 覆盖


def _resize_if_needed(frame, max_side):
    if max_side <= 0:
        return frame, 1.0
    h, w = frame.shape[:2]
    longest = max(h, w)
    if longest <= max_side:
        return frame, 1.0
    scale = max_side / longest
    resized = cv2.resize(frame, (int(round(w * scale)), int(round(h * scale))),
                          interpolation=cv2.INTER_AREA)
    return resized, scale


def _depth_to_heatmap_png(depth):
    """跟 phone_server.py 的 depth_to_heatmap 同一套 min-max 归一化 + INFERNO 配色，
    只是这里直接编码成 PNG bytes 返回给浏览器，不落盘。"""
    d = depth.copy()
    d_min, d_max = float(d.min()), float(d.max())
    if d_max > d_min + 1e-6:
        norm = (d - d_min) / (d_max - d_min)
    else:
        norm = np.zeros_like(d)
    norm = (norm * 255).astype(np.uint8)
    heat = cv2.applyColorMap(norm, cv2.COLORMAP_INFERNO)
    ok, buf = cv2.imencode('.png', heat)
    if not ok:
        raise RuntimeError("热力图编码失败")
    return buf.tobytes()


class InferHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass  # 静默 access log，只留我们自己打印的推理耗时

    def _cors(self):
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.end_headers()

    def do_GET(self):
        if self.path == '/health':
            self._send_json(200, {"status": "ok", "device": runner.device})
        else:
            self.send_error(404)

    def _send_json(self, status, payload):
        body = json.dumps(payload, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self._cors()
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != '/infer':
            self.send_error(404)
            return

        length = int(self.headers.get('Content-Length', 0))
        if length <= 0 or length > MAX_UPLOAD_BYTES:
            self._send_json(400, {"error": f"图片大小不合法或超过{MAX_UPLOAD_BYTES // (1024*1024)}MB上限"})
            return
        data = self.rfile.read(length)

        arr = np.frombuffer(data, np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            self._send_json(400, {"error": "无法解码图片，确认上传的是有效的 jpg/png"})
            return

        frame_r, scale = _resize_if_needed(frame, MAX_SIDE)

        try:
            with infer_lock:
                t0 = time.time()
                depth = runner.infer(frame_r)
                dt = time.time() - t0
        except Exception as e:
            self._send_json(500, {"error": f"推理失败: {e!r}"})
            return

        try:
            heat_png = _depth_to_heatmap_png(depth)
        except Exception as e:
            self._send_json(500, {"error": f"热力图生成失败: {e!r}"})
            return

        h, w = depth.shape
        payload = {
            "width": w,
            "height": h,
            "scale_applied": scale,
            "min_m": float(depth.min()),
            "max_m": float(depth.max()),
            "median_m": float(np.median(depth)),
            "infer_seconds": round(dt, 3),
            "heatmap_png_base64": base64.b64encode(heat_png).decode('ascii'),
        }
        print(f"[depth_server] {w}x{h} (scale={scale:.3f}) 推理{dt:.2f}s "
              f"depth[min={payload['min_m']:.2f} median={payload['median_m']:.2f} "
              f"max={payload['max_m']:.2f}]m")
        self._send_json(200, payload)


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def main():
    global MAX_SIDE
    ap = argparse.ArgumentParser(description="本地深度热力图预览服务（配合仓库根目录 depth_preview.html）")
    ap.add_argument('--port', type=int, default=8765)
    ap.add_argument('--max-side', type=int, default=2048,
                     help='上传图片长边超过这个像素就先等比缩小再推理，0=不缩放 (默认 %(default)s)')
    args = ap.parse_args()
    MAX_SIDE = args.max_side

    print("[depth_server] 加载 Depth-Anything-V2 metric 模型 ...")
    runner.load()
    print(f"[depth_server] 模型就绪, device={runner.device}")
    print("[depth_server] CUDA 预热中 ...")
    t0 = time.time()
    runner.infer(np.zeros((518, 388, 3), dtype=np.uint8))
    print(f"[depth_server] 预热完成 {time.time() - t0:.1f}s")

    httpd = ThreadingHTTPServer(('127.0.0.1', args.port), InferHandler)
    print(f"[depth_server] 监听 http://127.0.0.1:{args.port} （只本机可访问）")
    print("[depth_server] 用浏览器直接打开仓库根目录的 depth_preview.html，上传图片即可，Ctrl+C 停止服务")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == '__main__':
    main()
