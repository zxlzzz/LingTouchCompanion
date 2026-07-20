"""
Output sender — transmit braille frames to ESP32.

Supports:
  - Serial/UART (direct RPi ↔ ESP32 connection)
  - File output (for testing/logging)
  - Http POST (RPi → Backend → WebSocket → Phone → BLE → ESP32)
  - Network socket (raw TCP, legacy)

Protocol: raw 15-byte frames, one per line/time step.
No framing overhead — ESP32 BLE callback expects exactly 15 bytes.
"""

import time
import struct
import base64
import json
from pathlib import Path


class OutputSender:
    """Abstract frame sender."""

    def send(self, frame):
        """Send 15-byte frame (numpy array or bytes)."""
        raise NotImplementedError

    def close(self):
        pass


class SerialSender(OutputSender):
    """Send frames over UART to ESP32 directly.

    ESP32 UART0 (RX=GPIO44, TX=GPIO43 on S3) or UART1.
    Configure ESP32 to read raw bytes and push to BLE GATT.
    """

    def __init__(self, port="/dev/ttyUSB0", baudrate=115200):
        self.port = port
        self.baudrate = baudrate
        self._ser = None

    def open(self):
        import serial
        self._ser = serial.Serial(self.port, self.baudrate, timeout=0.1)
        print(f"[SerialSender] Opened {self.port} @ {self.baudrate}")

    def send(self, frame):
        if self._ser is None:
            self.open()
        raw = bytes(frame.tobytes() if hasattr(frame, 'tobytes') else frame)
        self._ser.write(raw)

    def close(self):
        if self._ser is not None:
            self._ser.close()
            self._ser = None


class FileSender(OutputSender):
    """Log frames to a file for testing/debugging."""

    def __init__(self, path="vision_output.bin"):
        self._f = open(path, "wb")

    def send(self, frame):
        raw = bytes(frame.tobytes() if hasattr(frame, 'tobytes') else frame)
        self._f.write(raw)
        self._f.flush()

    def close(self):
        self._f.close()


class NetworkSender(OutputSender):
    """Send frames over TCP to the Node.js backend, which relays to phone → BLE.

    The backend can add a route: POST /api/vision/frame { frame: [15 bytes base64] }
    Phone polls or WebSocket receives, then writes to BLE FFE1 characteristic.
    """

    def __init__(self, host="localhost", port=3001):
        self.host = host
        self.port = port
        self._sock = None

    def open(self):
        import socket
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.connect((self.host, self.port))
        print(f"[NetworkSender] Connected to {self.host}:{self.port}")

    def send(self, frame):
        if self._sock is None:
            self.open()
        raw = bytes(frame.tobytes() if hasattr(frame, 'tobytes') else frame)
        self._sock.sendall(raw)

    def close(self):
        if self._sock is not None:
            self._sock.close()
            self._sock = None


class HttpSender(OutputSender):
    """Send frames via HTTP POST to backend relay.

    Backend broadcasts to phone subscribers via WebSocket,
    phone then writes to BLE FFE1 characteristic → ESP32.

    Endpoint: POST /api/vision/frame
    Body: {"frame": "<base64>"}
    """

    def __init__(self, url="http://localhost:3000/api/vision/frame"):
        self.url = url
        self._session = None
        self._seq = 0

    def send(self, frame):
        import urllib.request

        raw = bytes(frame.tobytes() if hasattr(frame, 'tobytes') else frame)
        payload = json.dumps({"frame": base64.b64encode(raw).decode()}).encode()
        self._seq += 1

        try:
            req = urllib.request.Request(
                self.url,
                data=payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            urllib.request.urlopen(req, timeout=1)
        except Exception as e:
            # Don't spam on every frame — network is best-effort for relay
            if self._seq <= 1 or self._seq % 50 == 0:
                print(f"[HttpSender] send error (seq={self._seq}): {e}")


# ── Factory ──────────────────────────────────────────────

def create_sender(sender_type, **kwargs):
    """Create a sender by type string.

    Args:
        sender_type: "serial" | "file" | "http" | "network" | "none"
        **kwargs: passed to sender constructor

    Returns:
        OutputSender instance
    """
    if sender_type == "serial":
        return SerialSender(**kwargs)
    elif sender_type == "file":
        return FileSender(**kwargs)
    elif sender_type == "http":
        return HttpSender(**kwargs)
    elif sender_type == "network":
        return NetworkSender(**kwargs)
    elif sender_type == "none":
        return None
    else:
        raise ValueError(f"Unknown sender type: {sender_type}")
