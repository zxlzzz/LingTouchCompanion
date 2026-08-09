"""
frame_converter — 10x9 俯视栅格 <-> 15字节模组帧

从 vision/frame_converter.py 复制而来, 独立一份, 不 import vision/ 下任何文件
(两条路径完全解耦, 改这份不会有任何机会碰坏 vision/, 见仓库根目录 tasks.md)。
和 vision/ 版的关键差异:

1. 行的远近含义反过来了。vision/ 版(image-plane 管线, grid_mapper.py)是
   row0=画面顶部=远, row9=画面底部=近。visionss/ 版(topdown_pipeline.py 的
   depth_to_grid())是 row0=最近(0.5m), row9=最远(5m) —— 两条路径的栅格生成
   方式完全不同(俯视真实坐标 vs 图像平面), 这是各自独立做出的设计选择, 不是谁
   错了。ascii_preview() 的行首标签已按这份的约定改过, 不要direct照抄 vision/
   版的输出去对答案。
2. MODULE_ROT180 从"隐式写死在 _BIT_MAP 里"改成显式开关。vision/ 版的
   _BIT_MAP 已经是"180°反装"之后的版本(docstring 里写了"相对 prod 取
   (bit, 1-dr, 2-dc)"这个变换, 但没有把两个版本都留下来, 也没有开关)。这份
   把 prod(未反装)版本和反装变换都写出来, 用 MODULE_ROT180 常量选择,
   真机是反装的, 所以默认 True——和 vision/ 版当前行为完全一致, 只是把"为什么
   是这个映射"从注释挪到了可读的代码结构里。

grid_to_bytes 的字节格式(15字节, 每字节 bit0~bit5 对应一个模组的6个点,
模组 m(0..14) -> modRow=m//3, modCol=m%3, 占据栅格 3列x2行)和 vision/ 版
完全一致, 已在硬件上验证过, 固件侧不需要动。

模组在栅格中的覆盖范围:
  模组 m (0..14)  ->  modRow = m // 3 (0..4), modCol = m % 3 (0..2)
  占据栅格行 r = modRow*2 与 r+1，栅格列 c = modCol*3 .. c+2
  即每个模组在栅格上呈 3列 × 2行（模组物理为 2×3，横置安装）

15 字节数组的下标 m 直接对应固件的物理位置 pos-1（固件内部再经 posToChain 转链路序）。

改动记录: 2026-08-09 从 vision/frame_converter.py 复制, 加 MODULE_ROT180 开关,
加 mirror_grid_horizontal(), 改 ascii_preview() 远近标签方向。以后这两份
frame_converter.py 谁的 _BIT_MAP/MODULE_ROT180 变了, 记得同步另一份 +
sth2.html 的 gridToBytes()(sth2.html 目前还是老的 prod 映射, 没跟着"180°反装"
这次改动同步, 实验阶段不用它测试, 见 vision/frame_converter.py 的
_self_test 注释)。
"""

import numpy as np

GRID_COLS = 9
GRID_ROWS = 10
NUM_MODULES = 15

# 真机模组是 180° 反装的, 所以默认 True。改成 False 会用未反装的 prod 映射
# (跟 sth2.html 当前的 gridToBytes 一致, 但和真机实际接线不一致——除非以后
# 真的把模组翻回来重装, 否则不要改这个)。
MODULE_ROT180 = True

# 180°反装映射: (bit, dr, dc) —— 单一真源。直接照抄 vision/frame_converter.py 当前的
# _BIT_MAP(已在硬件上验证过), 不要在这里重新"猜"一份——之前猜过一次, 猜出来的
# prod->rot180 变换和 vision/ 版对不上, 已经改成"以 vision/ 版为准反推 prod"。
_BIT_MAP_ROT180 = [
    (0, 1, 0),
    (1, 1, 1),
    (2, 1, 2),
    (3, 0, 0),
    (4, 0, 1),
    (5, 0, 2),
]

# prod(未反装, 跟 sth2.html 当前 gridToBytes 一致)映射: 对 ROT180 应用同一个
# (bit, dr, dc) -> (bit, 1-dr, 2-dc) 变换反推出来(这个变换是对合的, 应用两次
# 等于没变, 所以从 ROT180 反推 prod 和从 prod 推 ROT180 用的是同一个变换)。
_BIT_MAP_PROD = [(bit, 1 - dr, 2 - dc) for bit, dr, dc in _BIT_MAP_ROT180]

_BIT_MAP = _BIT_MAP_ROT180 if MODULE_ROT180 else _BIT_MAP_PROD


def grid_to_bytes(frame):
    """90点(10x9) -> 15字节。

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


def mirror_grid_horizontal(grid):
    """左右镜像一个 (10,9) 栅格(或长度90的扁平序列)。

    设备贴身佩戴、摄像头朝外时，触点面朝向使用者，和摄像头拍到的画面
    左右相反，需要在发给设备前镜像一次抵消(和 vision/grid_mapper.py 的
    mirror_frame_horizontal 是同一个物理原因，这里独立实现一份)。只在
    "打包发送给硬件"这一步调用——预览/调试显示应保持摄像头原始视角。
    """
    g = np.asarray(grid).reshape(GRID_ROWS, GRID_COLS)
    return g[:, ::-1].copy()


def ascii_preview(frame):
    """把90点或15字节渲染成字符画，行首标注远近。

    row0=最近，row9=最远(topdown_pipeline.depth_to_grid 的约定，和 vision/
    版的图像平面约定方向相反，见文件头注释)。
    """
    a = np.asarray(frame)
    g = bytes_to_grid(a) if a.size == NUM_MODULES else a.reshape(GRID_ROWS, GRID_COLS)
    lines = []
    for r in range(GRID_ROWS):
        tag = "近" if r == 0 else ("远" if r == GRID_ROWS - 1 else "  ")
        cells = " ".join("●" if v else "·" for v in g[r])
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

    # 镜像自检: 镜像两次应该回到原状态, 且每行确实被左右翻转了
    g = rng.integers(0, 2, size=(GRID_ROWS, GRID_COLS), dtype=np.uint8)
    assert np.array_equal(mirror_grid_horizontal(mirror_grid_horizontal(g)), g)
    assert np.array_equal(mirror_grid_horizontal(g), g[:, ::-1])

    assert MODULE_ROT180 is True, "真机是180°反装, 这个开关不应该在默认配置里被改掉"
    # 180°反装映射下(与 vision/frame_converter.py 当前行为一致): 栅格左上角单点 -> M1 bit3 = 0x08
    f = np.zeros((GRID_ROWS, GRID_COLS), dtype=np.uint8)
    f[0, 0] = 1
    assert grid_to_bytes(f)[0] == 0x08
    # 栅格右下角单点 -> M15 bit2 = 0x04
    f = np.zeros((GRID_ROWS, GRID_COLS), dtype=np.uint8)
    f[9, 8] = 1
    assert grid_to_bytes(f)[14] == 0x04
    print(f"frame_converter 自检通过 (MODULE_ROT180={MODULE_ROT180})")


if __name__ == "__main__":
    _self_test()
