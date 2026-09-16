"""BLE transport for the experiment pipeline.

The link owns a background asyncio loop, reconnects until stopped, receives the
physical scan-button notification, and writes 15-byte tactile frames. A write
can optionally wait for the firmware refresh-complete notification so formal
experiment logs distinguish "write accepted" from "hardware refresh finished".
"""

import asyncio
import threading
import time

from bleak import BleakClient, BleakScanner

from frame_converter import grid_to_bytes, ascii_preview, hex_preview

DEVICE_NAME = "LingChu-Tactile"
CHAR_FFE1_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"
CHAR_FFE3_UUID = "0000ffe3-0000-1000-8000-00805f9b34fb"

EVT_REFRESH_DONE = 0x01
EVT_SCAN_REQUEST = 0x04


class ScanLink:
    """Reconnectable BLE link.

    ``frame_source`` is used only for the physical device button. It returns a
    10x9 grid or ``None``. Continuous experiment frames are sent explicitly by
    calling :meth:`send_now` from the PC-side scheduler.
    """

    SCAN_MIN_INTERVAL = 2.5
    RECONNECT_DELAY_S = 2.0

    def __init__(self, frame_source, device_name=DEVICE_NAME, verbose=True):
        self.frame_source = frame_source
        self.device_name = device_name
        self.verbose = verbose
        self.scan_count = 0

        self._loop = None
        self._loop_thread_id = None
        self._thread = None
        self._client = None
        self._connected = threading.Event()
        self._refresh_done = threading.Event()
        self._stop_requested = threading.Event()
        self._status_lock = threading.Lock()
        self._status = "stopped"
        self._last_scan_ts = 0.0

    @property
    def connected(self):
        client = self._client
        return bool(self._connected.is_set() and client is not None and client.is_connected)

    @property
    def status(self):
        with self._status_lock:
            return self._status

    def _set_status(self, value):
        with self._status_lock:
            changed = value != self._status
            self._status = value
        if changed and self.verbose:
            print(f"[BLE] {value}")

    def start(self):
        if self._thread and self._thread.is_alive():
            return self.connected
        self._stop_requested.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True, name="lingtouch-ble")
        self._thread.start()
        # Initial startup is bounded, but failure does not stop reconnection.
        if not self._connected.wait(timeout=15):
            print(f"[BLE] 暂未连接 {self.device_name}，后台继续重试；视觉处理仍可运行")
            return False
        return True

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop_thread_id = threading.get_ident()
        try:
            self._loop.run_until_complete(self._reconnect_loop())
        finally:
            self._client = None
            self._connected.clear()
            self._set_status("stopped")
            self._loop.close()
            self._loop = None

    async def _reconnect_loop(self):
        while not self._stop_requested.is_set():
            self._set_status(f"searching:{self.device_name}")
            try:
                device = await BleakScanner.find_device_by_name(self.device_name, timeout=8.0)
            except Exception as exc:
                print(f"[BLE] 搜索失败: {exc!r}")
                device = None

            if self._stop_requested.is_set():
                break
            if device is None:
                self._set_status("not_found;retrying")
                await self._interruptible_delay(self.RECONNECT_DELAY_S)
                continue

            try:
                async with BleakClient(device) as client:
                    self._client = client
                    await client.start_notify(CHAR_FFE3_UUID, self._on_notify)
                    self._connected.set()
                    self._set_status("connected")
                    while client.is_connected and not self._stop_requested.is_set():
                        await asyncio.sleep(0.2)
            except Exception as exc:
                if not self._stop_requested.is_set():
                    print(f"[BLE] 连接异常: {exc!r}")
            finally:
                self._client = None
                self._connected.clear()
                self._refresh_done.clear()

            if not self._stop_requested.is_set():
                self._set_status("disconnected;retrying")
                await self._interruptible_delay(self.RECONNECT_DELAY_S)

    async def _interruptible_delay(self, seconds):
        deadline = time.monotonic() + seconds
        while not self._stop_requested.is_set() and time.monotonic() < deadline:
            await asyncio.sleep(min(0.2, max(0.0, deadline - time.monotonic())))

    def _on_notify(self, _handle, data: bytearray):
        if not data:
            return
        evt_type = data[0]
        evt_data = data[1] if len(data) > 1 else 0
        if evt_type == EVT_REFRESH_DONE:
            self._refresh_done.set()
        elif evt_type == EVT_SCAN_REQUEST:
            threading.Thread(target=self._on_scan, daemon=True, name="lingtouch-button").start()
        elif self.verbose:
            print(f"[BLE] notify type=0x{evt_type:02X} data=0x{evt_data:02X}")

    def _on_scan(self):
        now = time.monotonic()
        if now - self._last_scan_ts < self.SCAN_MIN_INTERVAL:
            print("[BLE] 按键过密，忽略本次")
            return
        self._last_scan_ts = now
        self.scan_count += 1
        frame = self.frame_source()
        if frame is None:
            print(f"[SCAN #{self.scan_count}] 未生成新画面")
            return
        result = self.send_now(frame=frame, wait_refresh=True)
        print(f"\n[SCAN #{self.scan_count}] "
              f"{'刷新完成' if result['refresh_confirmed'] else '发送后未收到刷新确认'}")
        print(ascii_preview(frame))
        print(hex_preview(grid_to_bytes(frame)))

    async def _write_async(self, data):
        client = self._client
        if client is None or not client.is_connected:
            raise ConnectionError("BLE未连接")
        await client.write_gatt_char(CHAR_FFE1_UUID, bytes(data), response=False)

    def _write(self, data, timeout=5.0):
        loop = self._loop
        if loop is None or not loop.is_running() or not self.connected:
            return False, "not_connected"
        if threading.get_ident() == self._loop_thread_id:
            # Never block the BLE event loop on itself.
            task = loop.create_task(self._write_async(data))
            task.add_done_callback(self._log_write_result)
            return True, None
        fut = asyncio.run_coroutine_threadsafe(self._write_async(data), loop)
        try:
            fut.result(timeout=timeout)
            return True, None
        except Exception as exc:
            print(f"[BLE] 写入失败: {exc!r}")
            return False, repr(exc)

    @staticmethod
    def _log_write_result(task):
        try:
            exc = task.exception()
        except asyncio.CancelledError:
            return
        if exc is not None:
            print(f"[BLE] 写入失败: {exc!r}")

    def send_now(self, frame=None, wait_refresh=False, refresh_timeout=0.8):
        """Send one grid and return a structured delivery result."""
        if frame is None:
            self._on_scan()
            return {"write_ok": False, "refresh_confirmed": False, "error": "button_dispatched"}

        data = grid_to_bytes(frame)
        self._refresh_done.clear()
        t0 = time.perf_counter()
        write_ok, error = self._write(data)
        write_s = time.perf_counter() - t0
        refresh_confirmed = False
        refresh_wait_s = 0.0
        if write_ok and wait_refresh:
            t1 = time.perf_counter()
            refresh_confirmed = self._refresh_done.wait(timeout=refresh_timeout)
            refresh_wait_s = time.perf_counter() - t1
        return {
            "write_ok": bool(write_ok),
            "refresh_confirmed": bool(refresh_confirmed),
            "write_s": round(write_s, 4),
            "refresh_wait_s": round(refresh_wait_s, 4),
            "error": error,
        }

    def stop(self):
        self._stop_requested.set()
        client = self._client
        loop = self._loop
        if client is not None and loop is not None and loop.is_running():
            async def _cleanup():
                try:
                    await client.write_gatt_char(CHAR_FFE1_UUID, bytes(15), response=False)
                except Exception:
                    pass
                try:
                    await client.disconnect()
                except Exception:
                    pass

            try:
                fut = asyncio.run_coroutine_threadsafe(_cleanup(), loop)
                fut.result(timeout=3)
            except Exception:
                pass
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=10.0)
        self._connected.clear()
