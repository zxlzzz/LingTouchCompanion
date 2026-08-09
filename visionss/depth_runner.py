"""
depth_runner — 封装 Depth-Anything-V2 metric_depth 模型加载 + 单帧推理。

和 Depth-Anything-V2/metric_depth/run.py 走的是同一条推理路径(同一个
DepthAnythingV2 类、同一份 checkpoint、同一个 infer_image() 调用)，区别只是
这里常驻加载模型供 phone_server.py 反复调用，不是每帧起一个子进程——
run.py 那条路是离线批处理用的(见 TOPDOWN_VALIDATION.md 的标定/验证协议)，
在线服务这条路不能每次按键都重新加载一次 1.3GB 权重。

依赖 Depth-Anything-V2/ 官方仓库(clone 到仓库根目录，.gitignore 掉了) +
metric_depth/checkpoints/depth_anything_v2_metric_hypersim_vitl.pth 权重文件
(1.3GB，同样不进 git，需要手动放好，见根目录 CLAUDE.md 的环境说明)。

用法:
    from depth_runner import DepthRunner
    runner = DepthRunner()
    runner.load()                        # 显式加载，方便控制"什么时候扛下这1-2秒延迟"
    depth_m = runner.infer(bgr_frame)    # (H,W) float32，单位米，cv2 风格 BGR 输入

设备选择: DepthAnythingV2.infer_image() 内部会自己按 cuda>mps>cpu 的优先级
再选一次设备(不看外面传的参数)，所以这里 DepthRunner 的默认 device 选择用
同一套优先级，避免"模型在 cuda 上、输入张量被内部逻辑放到别的设备"这种不
一致。如果以后要强制 CPU 推理，两边都要改，不能只改这个类的 __init__。
"""

import sys
from pathlib import Path

import numpy as np
import torch

_REPO_ROOT = Path(__file__).resolve().parent.parent
_METRIC_DEPTH_DIR = _REPO_ROOT / "Depth-Anything-V2" / "metric_depth"
if str(_METRIC_DEPTH_DIR) not in sys.path:
    sys.path.insert(0, str(_METRIC_DEPTH_DIR))

DEFAULT_CHECKPOINT = _METRIC_DEPTH_DIR / "checkpoints" / "depth_anything_v2_metric_hypersim_vitl.pth"

_MODEL_CONFIGS = {
    'vits': {'encoder': 'vits', 'features': 64, 'out_channels': [48, 96, 192, 384]},
    'vitb': {'encoder': 'vitb', 'features': 128, 'out_channels': [96, 192, 384, 768]},
    'vitl': {'encoder': 'vitl', 'features': 256, 'out_channels': [256, 512, 1024, 1024]},
    'vitg': {'encoder': 'vitg', 'features': 384, 'out_channels': [1536, 1536, 1536, 1536]},
}


def _auto_device():
    if torch.cuda.is_available():
        return 'cuda'
    if torch.backends.mps.is_available():
        return 'mps'
    return 'cpu'


class DepthRunner:
    """常驻加载 Depth-Anything-V2 metric 模型，反复调用 infer() 做单帧米制深度推理。"""

    def __init__(self, encoder="vitl", checkpoint=DEFAULT_CHECKPOINT, max_depth=20.0,
                 input_size=518, device=None):
        if encoder not in _MODEL_CONFIGS:
            raise ValueError(f"未知 encoder={encoder!r}，可选 {list(_MODEL_CONFIGS)}")
        self.encoder = encoder
        self.checkpoint = Path(checkpoint)
        self.max_depth = max_depth
        self.input_size = input_size
        self.device = device or _auto_device()
        self._model = None

    def load(self):
        """加载权重。第一次调用较慢(读1.3GB文件+搬到显存)，故意不放进 __init__，
        由调用方决定什么时候扛这个延迟(通常是服务启动时，不是收到第一帧才做)。"""
        if self._model is not None:
            return
        from depth_anything_v2.dpt import DepthAnythingV2  # 延迟 import，见文件头 sys.path 处理

        if not self.checkpoint.exists():
            raise FileNotFoundError(
                f"[depth_runner] 权重文件不存在: {self.checkpoint}\n"
                "需要手动放置 depth_anything_v2_metric_hypersim_vitl.pth（1.3GB，不进 git），"
                "见仓库根目录 CLAUDE.md 的环境说明。"
            )
        print(f"[depth_runner] 加载 {self.encoder} @ {self.device} ...")
        cfg = _MODEL_CONFIGS[self.encoder]
        model = DepthAnythingV2(**{**cfg, 'max_depth': self.max_depth})
        model.load_state_dict(torch.load(str(self.checkpoint), map_location='cpu'))
        self._model = model.to(self.device).eval()
        print("[depth_runner] 模型就绪。")

    def infer(self, bgr_frame):
        """bgr_frame: (H,W,3) uint8 BGR (cv2 风格)。返回 (H,W) float32 米制深度。

        infer_image() 内部已经包了 @torch.no_grad()，这里不用再包一层。
        """
        if self._model is None:
            self.load()
        depth = self._model.infer_image(bgr_frame, self.input_size)
        return depth.astype(np.float32)


if __name__ == "__main__":
    # 自检: 用 pics/ascii 下随便一张图跑一遍, 只验证"能跑通", 不校验数值
    # (数值精度验证走 validate_distance.py, 那边有真实距离做对照)。
    import argparse
    import cv2

    ap = argparse.ArgumentParser(description="depth_runner 单帧自检")
    ap.add_argument("img", help="测试图片路径 (ASCII 文件名, 避开中文路径坑)")
    args = ap.parse_args()

    frame = cv2.imread(args.img)
    if frame is None:
        raise SystemExit(f"读不到图片: {args.img}（中文路径在这台机器上会乱码，用 ASCII 文件名）")

    runner = DepthRunner()
    depth = runner.infer(frame)
    print(f"depth shape={depth.shape} dtype={depth.dtype} "
          f"min={depth.min():.2f}m max={depth.max():.2f}m median={np.median(depth):.2f}m")
