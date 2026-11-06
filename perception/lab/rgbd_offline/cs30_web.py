"""Local CS30 RGB-D uploads and 9×6 obstacle evidence."""
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from io import BytesIO
import json
from pathlib import Path
import threading
from time import perf_counter
import traceback
import webbrowser

from rgbd_floor_demo import geometry, infer_floor_prior, load_floor_model
from geometry import Intrinsics
import numpy as np
from PIL import Image, UnidentifiedImageError
import torch


ROOT = Path(__file__).resolve().parent
# Same RGB intrinsics and working depth convention as the four-frame CS30 replay.
CAMERA = Intrinsics(960, 540, 465.5141296386719, 465.35321044921875,
                    488.48199462890625, 277.411376953125)
RAW_BYTES = CAMERA.width * CAMERA.height * 2
MAX_RGB_BYTES = 8 * 1024 * 1024


class Processor:
    def __init__(self, model_path):
        self.model_path = model_path
        self.floor_model = None
        self.lock = threading.Lock()

    def process(self, rgb_bytes, raw_bytes):
        try:
            with Image.open(BytesIO(rgb_bytes), formats=['PNG']) as image:
                if image.size != (CAMERA.width, CAMERA.height):
                    raise ValueError('RGB 图像必须为 960×540。')
                rgb = image.convert('RGB')
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise ValueError('无法读取 RGB PNG，请选择 RGBD_RGB 文件。') from exc

        depth = np.frombuffer(raw_bytes, dtype='<u2').reshape(CAMERA.height, CAMERA.width)
        depth = depth.astype(np.float32) / 1000.0
        with self.lock:
            if self.floor_model is None:
                self.floor_model = load_floor_model(self.model_path)
            start = perf_counter()
            prior = infer_floor_prior(rgb, *self.floor_model)
            result = geometry(depth, CAMERA, prior)
            elapsed_ms = round((perf_counter() - start) * 1000)
        return {
            'obstacle': result['coarse_obstacle_subcells'].tolist(),
            'ground': result['coarse_free_subcells'].tolist(),
            'unknown': result['coarse_unknown_subcells'].tolist(),
            'ground_valid': result['ground'] is not None,
            'status': result['status'],
            'elapsed_ms': elapsed_ms,
        }


class Handler(BaseHTTPRequestHandler):
    timeout = 30

    def send_body(self, status, content_type, body):
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        self.wfile.write(body)

    def send_json(self, status, payload):
        self.send_body(status, 'application/json; charset=utf-8',
                       json.dumps(payload, ensure_ascii=False).encode('utf-8'))

    def do_GET(self):
        if self.path == '/':
            self.send_body(200, 'text/html; charset=utf-8', (ROOT / 'cs30_web.html').read_bytes())
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != '/process':
            self.send_error(404)
            return
        try:
            if self.headers.get('Content-Type') != 'application/octet-stream':
                raise ValueError('请使用处理页面提交 RGB PNG 与深度 RAW。')
            try:
                size = int(self.headers.get('Content-Length', '0'))
                rgb_size = int(self.headers.get('X-RGB-Bytes', '0'))
            except ValueError as exc:
                raise ValueError('上传文件长度无效。') from exc
            if not 0 < size <= MAX_RGB_BYTES + RAW_BYTES:
                raise ValueError('上传文件为空或超过大小限制。')
            body = self.rfile.read(size)
            if len(body) != size:
                raise ValueError('上传未完成，请重试。')
            if not 0 < rgb_size <= MAX_RGB_BYTES:
                raise ValueError('请选择不超过 8 MiB 的 RGB PNG。')
            if size - rgb_size != RAW_BYTES:
                raise ValueError(f'深度 RAW 必须为 {RAW_BYTES:,} 字节（960×540，16 位）。')
            result = self.server.processor.process(body[:rgb_size], body[rgb_size:])
        except (ValueError, TimeoutError) as exc:
            self.send_json(400, {'error': str(exc) or '上传超时，请重试。'})
            return
        except Exception:
            traceback.print_exc()
            self.send_json(500, {'error': '处理失败，请查看启动窗口中的错误信息。'})
            return
        self.send_json(200, result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--open', action='store_true')
    parser.add_argument('--model-dir', type=Path, required=True,
                        help='Local SegFormer directory, e.g. perception/models/segformer-b0-ade')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('端口必须在 1–65535 之间。')
    model_path = args.model_dir.expanduser().resolve()
    for name in ('config.json', 'preprocessor_config.json', 'model.safetensors'):
        if not (model_path / name).is_file():
            parser.error(f'缺少本地地面分割模型文件 {model_path / name}')
    torch.set_num_threads(4)
    try:
        server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler)
    except OSError as exc:
        parser.error(f'无法监听本地端口 {args.port}。{exc}')
    with server:
        server.processor = Processor(model_path)
        url = f'http://127.0.0.1:{args.port}/'
        print(f'CS30 点阵处理器  {url}', flush=True)
        if args.open:
            webbrowser.open(url)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass


if __name__ == '__main__':
    main()
