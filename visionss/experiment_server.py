"""Shared PC-side runtime for LingTouch paper experiments.

Both experimental conditions use this exact capture, timing, logging and BLE
path. Only the final depth-to-output mapping differs:

* ``spatial``: 10x9 top-down tactile grid.
* ``single_point``: binary warning on one central module.

The phone keeps its camera preview open and responds to numbered capture
requests. The PC controls formal trials with ``start``/``stop`` and schedules
frames at approximately 1 Hz without queueing overlapping work.
"""

import argparse
from dataclasses import asdict
import datetime as dt
import json
import os
import re
import socket
import ssl
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from socketserver import ThreadingMixIn
from urllib.parse import parse_qs, urlparse

import cv2
import numpy as np

THIS_DIR = Path(__file__).resolve().parent
REPO_ROOT = THIS_DIR.parent
SINGLE_POINT_DIR = REPO_ROOT / "single_point"
for path in (str(THIS_DIR), str(SINGLE_POINT_DIR)):
    if path not in sys.path:
        sys.path.insert(0, path)

from alert_pipeline import depth_to_alert  # noqa: E402
from depth_runner import DepthRunner  # noqa: E402
from frame_converter import (  # noqa: E402
    GRID_COLS,
    GRID_ROWS,
    ascii_preview,
    grid_to_bytes,
    mirror_grid_horizontal,
)
from scan_link import ScanLink  # noqa: E402
from topdown_pipeline import CAM_H_TRUE, TopdownConfig, depth_to_grid  # noqa: E402


FX_DEFAULT = 3260.0
FX_BASE_WIDTH = 3072
FX_BASE_AR = 3072 / 4096
CAPTURE_ROTATE = cv2.ROTATE_90_CLOCKWISE
CAPTURE_TIMEOUT_S = 6.0
PHONE_HTML = THIS_DIR / "phone_camera.html"
RUN_ROOT = REPO_ROOT / "experiment_runs"

ALERT_MODULE = 10  # M11, central column, confirmed usable in the current device.
MAX_CONSECUTIVE_FAILURES = 3
MAX_UPLOAD_BYTES = 20 * 1024 * 1024


def utc_now():
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="milliseconds")


def safe_label(value):
    value = re.sub(r"[^\w.-]+", "_", (value or "").strip(), flags=re.UNICODE).strip("._")
    return value[:80]


def to_portrait(frame):
    h, w = frame.shape[:2]
    if w > h:
        return cv2.rotate(frame, CAPTURE_ROTATE)
    return frame


def resolve_fx(width, height, fx_base):
    ar = width / height
    if abs(ar - FX_BASE_AR) > 0.03:
        return None
    return fx_base * width / FX_BASE_WIDTH


def alert_to_grid(obstacle):
    grid = np.zeros((GRID_ROWS, GRID_COLS), dtype=np.uint8)
    if obstacle:
        row = (ALERT_MODULE // 3) * 2
        col = (ALERT_MODULE % 3) * 3
        grid[row:row + 2, col:col + 3] = 1
    return grid


def depth_to_heatmap(depth_map):
    finite = np.isfinite(depth_map)
    if not finite.any():
        return np.zeros((*depth_map.shape, 3), dtype=np.uint8)
    d_min = float(np.nanmin(depth_map))
    d_max = float(np.nanmax(depth_map))
    if d_max > d_min + 1e-6:
        normalized = (depth_map - d_min) / (d_max - d_min)
    else:
        normalized = np.zeros_like(depth_map)
    normalized = np.nan_to_num(normalized, nan=0.0, posinf=1.0, neginf=0.0)
    return cv2.applyColorMap((normalized * 255).astype(np.uint8), cv2.COLORMAP_INFERNO)


def render_grid_image(grid, cell_size=32):
    grid = np.asarray(grid).reshape(GRID_ROWS, GRID_COLS)
    image = np.zeros((GRID_ROWS * cell_size, GRID_COLS * cell_size, 3), dtype=np.uint8)
    for row in range(GRID_ROWS):
        for col in range(GRID_COLS):
            y0, y1 = row * cell_size, (row + 1) * cell_size
            x0, x1 = col * cell_size, (col + 1) * cell_size
            color = (0, 220, 80) if grid[row, col] else (20, 25, 30)
            cv2.rectangle(image, (x0, y0), (x1 - 1, y1 - 1), color, -1)
    return image


class CaptureBroker:
    """Thread-safe hand-off between HTTP uploads and the processing thread."""

    def __init__(self):
        self.lock = threading.Lock()
        self.capture_gen = 0
        self.awaiting_gen = None
        self.pending_frame = None
        self.pending_event = threading.Event()
        self.last_poll_monotonic = 0.0

    def poll_state(self):
        with self.lock:
            self.last_poll_monotonic = time.monotonic()
            return {
                "gen": self.capture_gen,
                "awaiting": self.awaiting_gen == self.capture_gen,
            }

    @property
    def phone_online(self):
        with self.lock:
            last_poll = self.last_poll_monotonic
        return last_poll > 0 and time.monotonic() - last_poll < 1.5

    def request_and_wait(self, timeout, cancel_event=None):
        with self.lock:
            self.capture_gen += 1
            generation = self.capture_gen
            self.awaiting_gen = generation
            self.pending_frame = None
            self.pending_event.clear()

        deadline = time.monotonic() + timeout
        got_frame = False
        cancelled = False
        while time.monotonic() < deadline:
            if cancel_event is not None and cancel_event.is_set():
                cancelled = True
                break
            remaining = deadline - time.monotonic()
            if self.pending_event.wait(timeout=min(0.1, max(0.0, remaining))):
                got_frame = True
                break
        with self.lock:
            frame = self.pending_frame if self.awaiting_gen == generation else None
            self.pending_frame = None
            if self.awaiting_gen == generation:
                self.awaiting_gen = None
        return generation, frame if got_frame else None, cancelled

    def receive(self, generation, frame):
        with self.lock:
            if generation != self.awaiting_gen or frame is None:
                return False
            self.pending_frame = frame
            self.pending_event.set()
            return True


class ThreadingHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True


def make_handler(app):
    class FrameHandler(BaseHTTPRequestHandler):
        def log_message(self, _format, *_args):
            pass

        def _json(self, payload, status=200):
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path in ("/", "/phone_camera.html"):
                if not PHONE_HTML.exists():
                    self.send_error(404)
                    return
                body = PHONE_HTML.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.send_header("Cache-Control", "no-store, no-cache, must-revalidate")
                self.end_headers()
                self.wfile.write(body)
            elif parsed.path == "/poll":
                self._json(app.broker.poll_state())
            elif parsed.path == "/health":
                self._json(app.status_payload())
            else:
                self.send_error(404)

        def do_POST(self):
            parsed = urlparse(self.path)
            if parsed.path != "/frame":
                self.send_error(404)
                return
            try:
                generation = int(parse_qs(parsed.query).get("gen", [""])[0])
            except (ValueError, IndexError):
                generation = None
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                length = 0
            if length <= 0 or length > MAX_UPLOAD_BYTES:
                self._json({"accepted": False, "error": "invalid_upload_size"}, status=413)
                return
            data = self.rfile.read(length)
            try:
                frame = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
            except Exception:
                frame = None
            accepted = generation is not None and app.broker.receive(generation, frame)
            self._json({"accepted": bool(accepted)})

    return FrameHandler


class ExperimentApp:
    def __init__(self, condition, fx, period_s, capture_timeout_s, export_every_frame,
                 no_ble, ble_device, topdown_config=None):
        if condition not in ("spatial", "single_point"):
            raise ValueError(f"unknown condition: {condition}")
        self.condition = condition
        self.fx = float(fx)
        if condition != "spatial" and topdown_config is not None:
            raise ValueError("A top-down profile applies only to the spatial condition")
        self.topdown_config = topdown_config or TopdownConfig()
        self.period_s = float(period_s)
        self.capture_timeout_s = float(capture_timeout_s)
        self.export_every_frame = bool(export_every_frame)
        self.no_ble = bool(no_ble)
        self.ble_device = ble_device

        self.runner = DepthRunner()
        self.broker = CaptureBroker()
        self.link = None
        self.process_lock = threading.Lock()
        self.sequence_lock = threading.Lock()
        self.log_lock = threading.Lock()
        self.frame_sequence = 0

        self.session_stop = threading.Event()
        self.shutdown_requested = threading.Event()
        self.session_thread = None
        self.session_id = None
        self.run_dir = None
        self.last_run_dir = None
        self.log_path = None
        self.consecutive_failures = 0

    @property
    def running(self):
        return bool(self.session_thread and self.session_thread.is_alive()
                    and not self.session_stop.is_set())

    def next_sequence(self):
        with self.sequence_lock:
            self.frame_sequence += 1
            return self.frame_sequence

    def load_model_and_warmup(self):
        print("[系统] 加载 Depth-Anything-V2 metric 模型…")
        self.runner.load()
        print("[系统] CUDA 预热…")
        started = time.perf_counter()
        # Experiment uploads are 1536x2048 portrait after rotation.
        self.runner.infer(np.zeros((2048, 1536, 3), dtype=np.uint8))
        print(f"[系统] 模型就绪，预热 {time.perf_counter() - started:.1f}s")

    def start_ble(self):
        if self.no_ble:
            return
        self.link = ScanLink(self.capture_for_button, device_name=self.ble_device)
        self.link.start()

    def status_payload(self):
        return {
            "condition": self.condition,
            "running": self.running,
            "session_id": self.session_id,
            "last_run_dir": str(self.last_run_dir) if self.last_run_dir else None,
            "phone_online": self.broker.phone_online,
            "ble": "disabled" if self.no_ble else (self.link.status if self.link else "starting"),
            "period_s": self.period_s,
            "export_every_frame": self.export_every_frame,
        }

    def _new_record(self, trigger, sequence):
        return {
            "event": "frame",
            "timestamp": utc_now(),
            "session_id": self.session_id,
            "condition": self.condition,
            "sequence": sequence,
            "trigger": trigger,
            "status": "started",
            "phone_online": self.broker.phone_online,
        }

    def _capture_and_process(self, trigger):
        with self.process_lock:
            sequence = self.next_sequence()
            record = self._new_record(trigger, sequence)
            total_started = time.perf_counter()

            capture_started = time.perf_counter()
            cancel_event = self.session_stop if trigger == "continuous" else None
            generation, frame, cancelled = self.broker.request_and_wait(
                self.capture_timeout_s, cancel_event=cancel_event)
            record["capture_generation"] = generation
            record["capture_s"] = round(time.perf_counter() - capture_started, 4)
            if frame is None:
                record["status"] = "capture_cancelled" if cancelled else "capture_timeout"
                record["total_s"] = round(time.perf_counter() - total_started, 4)
                return None, record, None

            frame = to_portrait(frame)
            height, width = frame.shape[:2]
            record["image_width"] = width
            record["image_height"] = height
            fx_effective = resolve_fx(width, height, self.fx)
            if fx_effective is None:
                record["status"] = "invalid_aspect_ratio"
                record["aspect_ratio"] = round(width / height, 5)
                record["total_s"] = round(time.perf_counter() - total_started, 4)
                return None, record, None
            record["fx_effective"] = round(fx_effective, 3)

            try:
                infer_started = time.perf_counter()
                depth = self.runner.infer(frame)
                record["inference_s"] = round(time.perf_counter() - infer_started, 4)

                mapping_started = time.perf_counter()
                if self.condition == "spatial":
                    grid = depth_to_grid(depth, fx=fx_effective, config=self.topdown_config)
                    record["topdown_parameters"] = asdict(self.topdown_config)
                    if grid is not None:
                        grid = mirror_grid_horizontal(grid)
                        record["active_dots"] = int(np.asarray(grid).sum())
                else:
                    result = depth_to_alert(depth, fx=fx_effective, cam_h_true=CAM_H_TRUE)
                    if result is None:
                        grid = None
                    else:
                        obstacle, count, threshold = result
                        grid = alert_to_grid(obstacle)
                        record.update({
                            "obstacle": bool(obstacle),
                            "obstacle_points": int(count),
                            "obstacle_threshold": int(threshold),
                        })
                record["mapping_s"] = round(time.perf_counter() - mapping_started, 4)
            except Exception as exc:
                record["status"] = "processing_error"
                record["error"] = repr(exc)
                record["total_s"] = round(time.perf_counter() - total_started, 4)
                return None, record, None

            if grid is None:
                record["status"] = "ground_fit_failed"
                record["total_s"] = round(time.perf_counter() - total_started, 4)
                return None, record, None

            record["status"] = "processed"
            record["frame_hex"] = grid_to_bytes(grid).hex()
            record["total_s"] = round(time.perf_counter() - total_started, 4)
            debug_payload = {"frame": frame, "depth": depth, "grid": grid}
            return grid, record, debug_payload

    def _deliver(self, grid):
        if self.no_ble:
            return {"disabled": True, "write_ok": None, "refresh_confirmed": None}
        if self.link is None:
            return {"disabled": False, "write_ok": False, "refresh_confirmed": False,
                    "error": "link_not_started"}
        result = self.link.send_now(grid, wait_refresh=True, refresh_timeout=0.8)
        result["disabled"] = False
        result["status"] = self.link.status
        return result

    def _run_and_send(self, trigger, export=False, log_event=True):
        cycle_started = time.perf_counter()
        grid, record, debug_payload = self._capture_and_process(trigger)
        if grid is not None and trigger == "continuous" and self.session_stop.is_set():
            record["status"] = "cancelled_before_delivery"
            grid = None
        if grid is not None:
            record["ble"] = self._deliver(grid)
            if not self.no_ble and not record["ble"].get("refresh_confirmed"):
                record["status"] = "delivery_unconfirmed"
            else:
                record["status"] = "ok"
        else:
            record["ble"] = {"disabled": self.no_ble, "write_ok": False,
                             "refresh_confirmed": False}
        record["cycle_s"] = round(time.perf_counter() - cycle_started, 4)

        if export and debug_payload is not None:
            try:
                record["export_dir"] = str(self._export_debug(debug_payload, record))
            except Exception as exc:
                record["export_error"] = repr(exc)
                print(f"[导出] 失败: {exc!r}")
        if log_event:
            self._log_event(record)
        self._print_frame_status(record)
        return grid, record

    def _export_debug(self, payload, record):
        base = self.run_dir
        if base is None:
            stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
            base = RUN_ROOT / f"manual_{self.condition}_{stamp}"
        out_dir = base / "exports" / f"frame_{record['sequence']:06d}_{int(time.time() * 1000)}"
        out_dir.mkdir(parents=True, exist_ok=False)
        cv2.imwrite(str(out_dir / "original.jpg"), payload["frame"])
        np.save(out_dir / "depth_raw.npy", payload["depth"])
        cv2.imwrite(str(out_dir / "depth_heat.jpg"), depth_to_heatmap(payload["depth"]))
        cv2.imwrite(str(out_dir / "grid.jpg"), render_grid_image(payload["grid"]))
        (out_dir / "meta.json").write_text(
            json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
        return out_dir

    def _log_event(self, record):
        if self.log_path is None:
            return
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        with self.log_lock:
            with self.log_path.open("a", encoding="utf-8") as handle:
                handle.write(line + "\n")

    @staticmethod
    def _print_frame_status(record):
        status = record["status"]
        seq = record["sequence"]
        if status == "ok":
            ble = record.get("ble", {})
            output = (f"active={record.get('active_dots')}" if "active_dots" in record
                      else f"obstacle={record.get('obstacle')}")
            delivery = "dry-run" if ble.get("disabled") else "refresh=ok"
            print(f"[帧 {seq:04d}] {record['cycle_s']:.2f}s {output} {delivery}")
        else:
            print(f"[帧 {seq:04d}] 失败: {status}")

    def capture_for_button(self):
        if self.running:
            print("[实验] 连续试次运行中，忽略物理按键的额外扫描请求")
            return None
        grid, record, _payload = self._capture_and_process("device_button")
        record["ble"] = {"delegated_to_scan_link": True}
        record["status"] = "processed_for_button" if grid is not None else record["status"]
        self._log_event(record)
        return grid

    def start_session(self, label=""):
        if self.running:
            print(f"[实验] 已在运行: {self.session_id}")
            return False
        if self.session_thread and self.session_thread.is_alive():
            self.session_thread.join(timeout=2.0)
        stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]
        suffix = safe_label(label)
        self.session_id = f"{stamp}_{self.condition}" + (f"_{suffix}" if suffix else "")
        self.run_dir = RUN_ROOT / self.session_id
        self.run_dir.mkdir(parents=True, exist_ok=False)
        self.log_path = self.run_dir / "events.jsonl"
        self.frame_sequence = 0
        self.consecutive_failures = 0
        self.session_stop.clear()
        self._log_event({
            "event": "session_start",
            "timestamp": utc_now(),
            "session_id": self.session_id,
            "condition": self.condition,
            "period_s": self.period_s,
            "fx_base": self.fx,
            "cam_h_true": self.topdown_config.cam_h_true if self.condition == "spatial" else CAM_H_TRUE,
            "topdown_parameters": asdict(self.topdown_config) if self.condition == "spatial" else None,
            "export_every_frame": self.export_every_frame,
            "ble_device": None if self.no_ble else self.ble_device,
        })
        self.session_thread = threading.Thread(
            target=self._session_loop, daemon=True, name="lingtouch-experiment")
        self.session_thread.start()
        print(f"[实验] 开始: {self.session_id}")
        return True

    def _session_loop(self):
        next_start = time.perf_counter()
        stop_reason = "operator_stop"
        try:
            while not self.session_stop.is_set() and not self.shutdown_requested.is_set():
                target_start = next_start
                _grid, record = self._run_and_send(
                    "continuous", export=self.export_every_frame, log_event=False)
                finished = time.perf_counter()
                record["schedule_lag_s"] = round(max(0.0, finished - (target_start + self.period_s)), 4)
                self._log_event(record)

                if record["status"] == "ok":
                    self.consecutive_failures = 0
                else:
                    self.consecutive_failures += 1
                if self.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
                    stop_reason = f"auto_pause_after_{MAX_CONSECUTIVE_FAILURES}_failures"
                    self._log_event({
                        "event": "auto_pause",
                        "timestamp": utc_now(),
                        "reason": stop_reason,
                    })
                    print(f"[实验] 连续 {MAX_CONSECUTIVE_FAILURES} 帧失败，已自动暂停")
                    self.session_stop.set()
                    break

                next_start += self.period_s
                if next_start < finished:
                    # Do not queue missed frames. Resume one period after now.
                    next_start = finished
                self.session_stop.wait(max(0.0, next_start - time.perf_counter()))
        finally:
            if self.shutdown_requested.is_set():
                stop_reason = "shutdown"
            self._log_event({
                "event": "session_end",
                "timestamp": utc_now(),
                "session_id": self.session_id,
                "reason": stop_reason,
                "frames": self.frame_sequence,
            })
            self.last_run_dir = self.run_dir
            self.log_path = None
            self.run_dir = None
            self.session_stop.set()

    def stop_session(self):
        if not self.session_thread or not self.session_thread.is_alive():
            print("[实验] 当前未运行")
            return False
        self.session_stop.set()
        if threading.current_thread() is not self.session_thread:
            self.session_thread.join(timeout=self.capture_timeout_s + 3.0)
        print(f"[实验] 已停止: {self.session_id}")
        return True

    def manual_capture(self, export=False):
        if self.running:
            print("[实验] 连续试次运行中；请先 stop，再执行单帧")
            return
        grid, _record = self._run_and_send("manual_export" if export else "manual", export=export)
        if grid is not None:
            print(ascii_preview(grid))

    def print_status(self):
        status = self.status_payload()
        print(f"[状态] condition={status['condition']} running={status['running']} "
              f"phone={'online' if status['phone_online'] else 'offline'} "
              f"BLE={status['ble']} session={status['session_id'] or '-'}")

    def console_loop(self):
        print("\n电脑控制: start [标签] | stop | snap | export | status | help | q\n")
        while not self.shutdown_requested.is_set():
            try:
                command = input("> ").strip()
            except EOFError:
                command = "q"
            if not command:
                continue
            action, _, argument = command.partition(" ")
            action = action.lower()
            if action == "start":
                self.start_session(argument)
            elif action == "stop":
                self.stop_session()
            elif action in ("snap", "capture"):
                self.manual_capture(export=False)
            elif action == "export":
                self.manual_capture(export=True)
            elif action == "status":
                self.print_status()
            elif action == "help":
                print("start [标签] 开始连续试次；stop 停止；snap 单帧；"
                      "export 单帧并保存完整素材；status 查看连接；q 退出")
            elif action in ("q", "quit", "exit"):
                break
            else:
                print("未知命令；输入 help 查看")

    def shutdown(self):
        self.shutdown_requested.set()
        self.session_stop.set()
        if self.session_thread and self.session_thread.is_alive():
            self.session_thread.join(timeout=self.capture_timeout_s + 3.0)
        if self.link is not None:
            self.link.stop()


def get_ip():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        sock.close()


def ensure_cert():
    cert_file = THIS_DIR / "cert.pem"
    key_file = THIS_DIR / "key.pem"
    if cert_file.exists() and key_file.exists():
        return str(cert_file), str(key_file)

    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    key_file.write_bytes(key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ))
    now = dt.datetime.now(dt.timezone.utc)
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "LingTouch")])
    cert = (x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now)
            .not_valid_after(now + dt.timedelta(days=3650))
            .add_extension(x509.SubjectAlternativeName([x509.DNSName("localhost")]), critical=False)
            .sign(key, hashes.SHA256()))
    cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    return str(cert_file), str(key_file)


def main(default_condition="spatial", default_port=8760):
    parser = argparse.ArgumentParser(description="LingTouch paper experiment runtime")
    parser.add_argument("--condition", choices=("spatial", "single_point"),
                        default=default_condition)
    parser.add_argument("--port", type=int, default=default_port)
    parser.add_argument("--ble-device", default="LingChu-Tactile")
    parser.add_argument("--no-ble", action="store_true")
    parser.add_argument("--fx", type=float, default=FX_DEFAULT)
    parser.add_argument("--topdown-profile", type=Path,
                        help="spatial mapping JSON; omit to reproduce legacy parameters")
    parser.add_argument("--period", type=float, default=1.0,
                        help="continuous trial target period in seconds")
    parser.add_argument("--capture-timeout", type=float, default=CAPTURE_TIMEOUT_S)
    parser.add_argument("--export-every-frame", action="store_true",
                        help="debug only: save image/depth/grid for every frame")
    args = parser.parse_args()
    if args.period <= 0:
        parser.error("--period must be positive")
    if args.topdown_profile and args.condition != "spatial":
        parser.error("--topdown-profile requires --condition spatial")
    profile = TopdownConfig.load(args.topdown_profile) if args.topdown_profile else None

    app = ExperimentApp(
        condition=args.condition,
        fx=args.fx,
        period_s=args.period,
        capture_timeout_s=args.capture_timeout,
        export_every_frame=args.export_every_frame,
        no_ble=args.no_ble,
        ble_device=args.ble_device,
        topdown_config=profile,
    )
    app.load_model_and_warmup()

    cert, key = ensure_cert()
    httpd = ThreadingHTTPServer(("0.0.0.0", args.port), make_handler(app))
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(cert, key)
    httpd.socket = context.wrap_socket(httpd.socket, server_side=True)
    server_thread = threading.Thread(target=httpd.serve_forever, daemon=True, name="lingtouch-http")
    server_thread.start()

    ip = get_ip()
    print(f"[系统] 条件: {args.condition}")
    print(f"[系统] 手机打开: https://{ip}:{args.port}")
    print("[系统] 上传按1536x2048处理；完整素材默认不保存")
    app.start_ble()

    try:
        app.console_loop()
    except KeyboardInterrupt:
        pass
    finally:
        app.shutdown()
        httpd.shutdown()
        httpd.server_close()


if __name__ == "__main__":
    main()
