"""
scan_link — BLE 侧的"扫描请求 → 下发"触发器。

设备通过 FFE3 (notify) 广播状态事件，扫描按键被按下时上报
EVT_SCAN_REQUEST (0x04, 见固件 braille_15module_prod.ino)。
本模块用 bleak 连接 "LingChu-Tactile"、订阅 FFE3，收到 0x04 后
向回调索取当前 90 点栅格，打包成 15 字节写入 FFE1 (write)。
UUID 与写法均与 sth2.html 的 Web Bluetooth 实现保持一致。

bleak 是异步库；这里起一个独立线程跑自己的 event loop，对外仍暴露
start()/send_now()/stop() 同步接口，供 phone_server.py 直接调用。

从 vision/scan_link.py 复制而来，基本不动，只是 `from frame_converter import ...`
现在解析到的是同目录下 visionss/frame_converter.py（180°反装映射+ 新的远近栅格
约定），不是 vision/ 那份——BLE 协议/帧格式本身没有变化，不需要动这个文件的逻辑。
"""

import asyncio
import threading

from bleak import BleakClient, BleakScanner

from frame_converter import grid_to_bytes, ascii_preview, hex_preview

DEVICE_NAME = "LingChu-Tactile"
CHAR_FFE1_UUID = "0000ffe1-0000-1000-8000-00805f9b34fb"   # write
CHAR_FFE3_UUID = "0000ffe3-0000-1000-8000-00805f9b34fb"   # notify
EVT_SCAN_REQUEST = 0x04


class ScanLink:
    """
    frame_source: 无参可调用对象，返回长度90的序列（或 (10,9) 数组），
                  没有可用帧时返回 None。
    """

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

    def start(self):
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        if not self._connected.wait(timeout=15):
            print(f"[scan_link] 连接 {self.device_name} 超时，跳过设备输出（预览仍可用）")
            return False
        return True

    def _run_loop(self):
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        self._loop_thread_id = threading.get_ident()
        self._loop.run_until_complete(self._connect_and_serve())

    async def _connect_and_serve(self):
        print(f"[scan_link] 搜索 {self.device_name} ...")
        device = await BleakScanner.find_device_by_name(self.device_name, timeout=15.0)
        if device is None:
            print(f"[scan_link] 未找到设备 {self.device_name}")
            return

        async with BleakClient(device) as client:
            self._client = client
            await client.start_notify(CHAR_FFE3_UUID, self._on_notify)
            self._connected.set()
            print(f"[scan_link] 已连接 {self.device_name}，等待扫描请求 (0x04)…")
            try:
                while client.is_connected:
                    await asyncio.sleep(0.5)
            finally:
                self._client = None
                self._connected.clear()
                print("[scan_link] BLE 连接断开")

    def _on_notify(self, _handle, data: bytearray):
        if len(data) < 1:
            return
        evt_type = data[0]
        evt_data = data[1] if len(data) > 1 else 0
        if evt_type == EVT_SCAN_REQUEST:
            self._on_scan()
        elif self.verbose:
            print(f"[scan_link] < notify type=0x{evt_type:02X} data=0x{evt_data:02X}")

    SCAN_MIN_INTERVAL = 2.5  # 固件中断路径有 prevData 失步 bug，去抖规避连击

    def _on_scan(self):
        import time as _t
        now = _t.time()
        if now - getattr(self, "_last_scan_ts", 0.0) < self.SCAN_MIN_INTERVAL:
            print("[scan_link] 按键过密，忽略本次")
            return
        self._last_scan_ts = now
        self.scan_count += 1
        frame = self.frame_source()
        if frame is None:
            print(f"[SCAN #{self.scan_count}] 尚无可用画面，忽略")
            return
        data = grid_to_bytes(frame)
        self._write(data)
        print(f"\n[SCAN #{self.scan_count}] 已下发 15 字节")
        print(ascii_preview(frame))
        print(hex_preview(data))

    def _write(self, data):
        if self._client is None or self._loop is None:
            return
        coro = self._client.write_gatt_char(CHAR_FFE1_UUID, bytes(data), response=False)

        if threading.get_ident() == self._loop_thread_id:
            # 已经在 event loop 自己的线程里（BLE notify 回调触发）——
            # 不能像下面那样同步等待结果，那样会等自己把协程跑完，直接死锁。
            # 用 create_task 扔进循环，让它跟着 loop 自然往前走就行。
            task = self._loop.create_task(coro)
            task.add_done_callback(self._log_write_result)
        else:
            # 来自其他线程（如 send_now() 被主线程调用），可以安全阻塞等待。
            fut = asyncio.run_coroutine_threadsafe(coro, self._loop)
            try:
                fut.result(timeout=5)
            except Exception as e:
                print(f"[scan_link] 写入失败: {e!r}")

    def _log_write_result(self, task):
        exc = task.exception()
        if exc is not None:
            print(f"[scan_link] 写入失败: {exc!r}")

    def send_now(self, frame=None):
        """手动触发一次下发（键盘空格等场景）。"""
        if self._client is None:
            return
        if frame is None:
            self._on_scan()
        else:
            self._write(grid_to_bytes(frame))

    def stop(self):
        if self._client is not None and self._loop is not None:
            async def _cleanup(client):
                try:
                    await client.write_gatt_char(CHAR_FFE1_UUID, bytes(15), response=False)
                except Exception:
                    pass
                await client.disconnect()

            fut = asyncio.run_coroutine_threadsafe(_cleanup(self._client), self._loop)
            try:
                fut.result(timeout=5)
            except Exception:
                pass
        if self._thread:
            self._thread.join(timeout=5.0)
