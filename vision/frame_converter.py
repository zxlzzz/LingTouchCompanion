"""
frame_converter — 90点扁平帧 <-> 15字节模组帧

视觉管线输出：90 字节 / 90 元素数组，9列 × 10行，行优先，row0=远，row9=近。
设备接收：15 字节，每字节 bit0~bit5 对应该模组的 6 个点。

模组在 9×10 栅格中的覆盖范围（与 sth2.html gridToBytes 完全一致，已在硬件上验证）：
  模组 m (0..14)  ->  modRow = m // 3 (0..4), modCol = m % 3 (0..2)
  占据栅格行 r = modRow*2 与 r+1，栅格列 c = modCol*3 .. c+2
  即每个模组在栅格上呈 3列 × 2行（模组物理为 2×3，横置安装）

位序（注意每行是 右→左）：
  bit0 = g[r  ][c+2]    bit1 = g[r  ][c+1]    bit2 = g[r  ][c]
  bit3 = g[r+1][c+2]    bit4 = g[r+1][c+1]    bit5 = g[r+1][c]

15 字节数组的下标 m 直接对应固件的物理位置 pos-1（固件内部再经 posToChain 转链路序）。
"""

import numpy as np

GRID_COLS = 9
GRID_ROWS = 10
NUM_MODULES = 15

# (bit, dr, dc) —— 单一真源，正反变换共用
_BIT_MAP = [
    (0, 0, 2),
    (1, 0, 1),
    (2, 0, 0),
    (3, 1, 2),
    (4, 1, 1),
    (5, 1, 0),
]


def grid_to_bytes(frame):
    """90点 -> 15字节。

    frame: 长度90的一维序列 / (10,9) 数组 / bytes，非零即为凸起。
    返回: bytes，长度15。
    """
    g = np.asarray(frame).reshape(GRID_ROWS, GRID_COLS)
    out = bytearray(NUM_MODULES)
    for m in range(NUM_MODULES):
        r = (m // 3) * 2
        c = (m % 3) * 3
        b = 0
        for bit, dr, dc in _BIT_MAP:
            if g[r + dr, c + dc]:
                b |= (1 << bit)
        out[m] = b
    return bytes(out)


def bytes_to_grid(data):
    """15字节 -> (10,9) uint8 栅格。用于回读校验与预览。"""
    g = np.zeros((GRID_ROWS, GRID_COLS), dtype=np.uint8)
    for m in range(NUM_MODULES):
        r = (m // 3) * 2
        c = (m % 3) * 3
        b = data[m]
        for bit, dr, dc in _BIT_MAP:
            if b & (1 << bit):
                g[r + dr, c + dc] = 1
    return g


def ascii_preview(frame):
    """把90点或15字节渲染成字符画，行首标注远近。"""
    a = np.asarray(frame)
    g = bytes_to_grid(a) if a.size == NUM_MODULES else a.reshape(GRID_ROWS, GRID_COLS)
    lines = []
    for r in range(GRID_ROWS):
        tag = "远" if r == 0 else ("近" if r == GRID_ROWS - 1 else "  ")
        cells = " ".join("●" if v else "·" for v in g[r])
        sep = "  |" if r % 2 == 1 and r != GRID_ROWS - 1 else "   "
        lines.append(f"{tag} {cells}")
        if r % 2 == 1 and r != GRID_ROWS - 1:
            lines.append("   " + "-" * (GRID_COLS * 2 - 1))
    return "\n".join(lines)


def hex_preview(data):
    """按 3 列排布打印 15 字节，便于与 sth2.html 的 Hex 面板逐字节比对。"""
    lines = []
    for row in range(5):
        cells = []
        for col in range(3):
            m = row * 3 + col
            cells.append(f"M{m+1:>2}:{data[m]:02X}")
        lines.append("  ".join(cells))
    return "\n".join(lines)


def _self_test():
    rng = np.random.default_rng(0)
    for _ in range(2000):
        g = rng.integers(0, 2, size=(GRID_ROWS, GRID_COLS), dtype=np.uint8)
        assert np.array_equal(bytes_to_grid(grid_to_bytes(g)), g), "往返不一致"

    # 单点扫描：第 i 个栅格点必须且只能点亮一个 bit
    for i in range(GRID_ROWS * GRID_COLS):
        f = np.zeros(GRID_ROWS * GRID_COLS, dtype=np.uint8)
        f[i] = 1
        d = grid_to_bytes(f)
        assert sum(bin(x).count("1") for x in d) == 1, f"点{i}映射丢失或重复"

    # 与 sth2.html 手工核对的样例：栅格左上角单点 -> M1 bit2 = 0x04
    f = np.zeros((GRID_ROWS, GRID_COLS), dtype=np.uint8)
    f[0, 0] = 1
    assert grid_to_bytes(f)[0] == 0x04
    # 栅格右下角单点 -> M15 bit3 = 0x08
    f = np.zeros((GRID_ROWS, GRID_COLS), dtype=np.uint8)
    f[9, 8] = 1
    assert grid_to_bytes(f)[14] == 0x08
    print("frame_converter 自检通过")


if __name__ == "__main__":
    _self_test()