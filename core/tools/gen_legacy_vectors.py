#!/usr/bin/env python3
"""用硬件验证过的 experiments/chi2027/visionss/frame_converter.py 生成旧板编码的测试向量。

C++ 编码器（core/src/tactile_legacy.cpp）在 core/tests/test_tactile_legacy.cpp 里逐字节对比这些向量。

    python core/tools/gen_legacy_vectors.py          # 重新生成 core/tests/data/legacy_vectors.txt
    python core/tools/gen_legacy_vectors.py --check  # 只检查已提交的向量是否仍与 frame_converter.py 一致

向量格式（每行一个）：
    grid  <rot180 0|1> <90 位 0/1，10×9 行优先，row 0 最远> <15 字节 hex>
        = frame_converter.grid_to_bytes（_BIT_MAP 取 ROT180 或 PROD）
    chain <rot180 0|1> <mirror 0|1> <flat|raised> <54 位 0/1/2，9×6 行优先，row 0 最远> <15 字节 hex>
        = 9×6 放进 10×9 最近 6 行（其余 4 行全平，2 按策略）→ 可选 mirror_grid_horizontal → grid_to_bytes
需要 numpy（frame_converter.py 依赖它）。
"""

import argparse
import hashlib
import importlib.util
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
CORE = HERE.parent
FRAME_CONVERTER = CORE.parent / "experiments" / "chi2027" / "visionss" / "frame_converter.py"
TARGET = CORE / "tests" / "data" / "legacy_vectors.txt"


def load_frame_converter():
    spec = importlib.util.spec_from_file_location("frame_converter_reference", FRAME_CONVERTER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def generate():
    import numpy as np

    fc = load_frame_converter()
    rng = np.random.default_rng(20261028)
    lines = []

    def grids_10x9():
        yield np.zeros((10, 9), dtype=np.uint8)
        yield np.ones((10, 9), dtype=np.uint8)
        for i in range(90):
            g = np.zeros(90, dtype=np.uint8)
            g[i] = 1
            yield g.reshape(10, 9)
        for _ in range(200):
            yield rng.integers(0, 2, size=(10, 9), dtype=np.uint8)

    for rot180, bit_map in ((1, fc._BIT_MAP_ROT180), (0, fc._BIT_MAP_PROD)):
        fc._BIT_MAP = bit_map
        for g in grids_10x9():
            bits = "".join(str(int(v)) for v in g.reshape(-1))
            lines.append(f"grid {rot180} {bits} {fc.grid_to_bytes(g).hex()}")

    def place(states, policy):
        board = np.zeros((10, 9), dtype=np.uint8)
        for r in range(6):
            for c in range(9):
                s = int(states[r, c])
                board[r + 4, c] = 1 if s == 1 or (s == 2 and policy == "raised") else 0
        return board

    states_list = [np.full((6, 9), s, dtype=np.uint8) for s in (0, 1, 2)]
    states_list += [rng.integers(0, 3, size=(6, 9), dtype=np.uint8) for _ in range(100)]
    for rot180, bit_map in ((1, fc._BIT_MAP_ROT180), (0, fc._BIT_MAP_PROD)):
        fc._BIT_MAP = bit_map
        for mirror in (0, 1):
            for policy in ("flat", "raised"):
                for states in states_list:
                    board = place(states, policy)
                    if mirror:
                        board = fc.mirror_grid_horizontal(board)
                    cells = "".join(str(int(v)) for v in states.reshape(-1))
                    lines.append(f"chain {rot180} {mirror} {policy} {cells} {fc.grid_to_bytes(board).hex()}")

    digest = hashlib.sha256(FRAME_CONVERTER.read_bytes()).hexdigest()
    header = [
        "# 由 core/tools/gen_legacy_vectors.py 用 experiments/chi2027/visionss/frame_converter.py 生成，不要手改。",
        f"# frame_converter.py sha256: {digest}",
    ]
    return "\n".join(header + lines) + "\n"


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="只检查，不写文件；不一致时退出码为 1")
    args = ap.parse_args()
    try:
        text = generate()
    except ImportError as exc:
        print(f"跳过：缺少依赖（{exc}）", file=sys.stderr)
        return 77  # CTest 里按 SKIP 处理
    if args.check:
        current = TARGET.read_text(encoding="utf-8") if TARGET.exists() else ""
        if current != text:
            print(f"{TARGET} 与 frame_converter.py 生成的结果不一致，请重新运行本脚本", file=sys.stderr)
            return 1
        print("legacy vectors are up to date")
        return 0
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    TARGET.write_text(text, encoding="utf-8", newline="\n")
    print(f"wrote {TARGET} ({text.count(chr(10)) - 2} vectors)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
