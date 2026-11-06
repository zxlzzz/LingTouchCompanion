#!/usr/bin/env python3
"""从 cs30/startup_sequence.json 生成 C++ 启动序列表（不要手抄）。

    python vision/native/tools/gen_startup_sequence.py          # 重新生成
    python vision/native/tools/gen_startup_sequence.py --check  # 只检查已提交的表是否与 JSON 一致

规则来自 cs30/REPORT.md：
- 控制请求的 setup 和 OUT 数据逐字节取自 JSON（SDK 实际发出的 41 条）。
- 第 9 步：SET_CUR 0xa700 之后先处理约 270 ms 的事件，再发 SET_CUR 0xa300。这条等待
  不在 JSON 里，由本脚本按 REPORT 加到 0xa700 那一步的 settle_ms 上。
- 控制请求超时（15 s）等常量在 cs30_protocol.h 里，不在表里。
"""

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parents[2] / "cs30" / "startup_sequence.json"
TARGET = HERE.parent / "src" / "cs30_startup_sequence.inc"

SETTLE_AFTER_A700_MS = 270  # REPORT.md 第 9 步


def generate(source_bytes):
    steps = json.loads(source_bytes)
    lines = []
    data_arrays = []
    controls = 0
    queue_iso = 0
    for i, step in enumerate(steps):
        kind = step["kind"]
        if kind == "control":
            controls += 1
            setup = bytes(step["setup"])
            if len(setup) != 8:
                raise ValueError(f"step {i}: setup must be 8 bytes")
            request_type, request, value, index, length = struct.unpack("<BBHHH", setup)
            settle = 0
            data_name = "nullptr"
            data_len = 0
            if request_type & 0x80:
                if step.get("data"):
                    raise ValueError(f"step {i}: IN request must not carry OUT data")
            else:
                data = bytes(step.get("data") or [])
                if len(data) != length:
                    raise ValueError(f"step {i}: OUT data length {len(data)} != wLength {length}")
                data_name = f"kStep{i:02d}Data"
                data_len = len(data)
                body = ", ".join(f"0x{b:02x}" for b in data)
                data_arrays.append(f"constexpr uint8_t {data_name}[] = {{{body}}};")
                if request_type == 0x21 and request == 0x01 and value == 0xA700:
                    settle = SETTLE_AFTER_A700_MS
            lines.append(
                f"    control(0x{request_type:02x}, 0x{request:02x}, 0x{value:04x}, 0x{index:04x}, {length}, "
                f"{data_name}, {data_len}, {settle}),  // {i}"
            )
        elif kind == "alt":
            lines.append(f"    set_alt({int(step['interface'])}, {int(step['alt'])}),  // {i}")
        elif kind == "queue_iso":
            queue_iso += 1
            lines.append(
                f"    queue_iso({int(step['count'])}, {int(step['length'])}, {int(step['packets'])}, "
                f"{int(step['timeout'])}),  // {i}"
            )
        else:
            raise ValueError(f"step {i}: unknown kind {kind!r}")
    if controls != 41 or queue_iso != 1:
        raise ValueError(f"expected 41 control requests and 1 queue_iso step, got {controls} and {queue_iso}")
    if not any(" 270)," in line for line in lines):
        raise ValueError("SET_CUR 0xa700 not found; cannot place the 270 ms settle step")

    digest = hashlib.sha256(source_bytes).hexdigest()
    out = [
        "// 由 vision/native/tools/gen_startup_sequence.py 从 cs30/startup_sequence.json 生成，不要手改。",
        f"// startup_sequence.json sha256: {digest}",
        f"// {len(steps)} 步：{controls} 条控制请求、{len(steps) - controls - queue_iso} 次切换接口、{queue_iso} 次挂等时传输。",
        "",
        *data_arrays,
        "",
        "const Step kStartupSequence[] = {",
        *lines,
        "};",
        "",
    ]
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="只检查，不写文件；不一致时退出码为 1")
    args = ap.parse_args()
    text = generate(SOURCE.read_bytes())
    if args.check:
        current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
        if current != text:
            print(f"{TARGET} 与 {SOURCE} 不一致，请重新运行本脚本", file=sys.stderr)
            return 1
        print("startup sequence table is up to date")
        return 0
    TARGET.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {TARGET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
