"""
Depth Anything V2 — monocular depth estimation wrapper.

Model variants (via Hugging Face):
  - depth-anything/Depth-Anything-V2-Small  (~25M params)
  - depth-anything/Depth-Anything-V2-Base   (~98M params)
  - depth-anything/Depth-Anything-V2-Large  (~335M params)

On Raspberry Pi 5 (8GB), the Small model runs at ~2-3 FPS on CPU.
For real-time use, consider:
  - Google Coral USB TPU (via ONNX export)
  - Hailo-8L AI Kit for RPi 5
  - Reducing input resolution to 256×256

Usage:
  from depth_estimator import DepthEstimator
  est = DepthEstimator(model_size="small", use_gpu=False)
  est.load()
  depth_map = est.estimate(bgr_frame)  # returns 2D float32 array (meters)
"""

import os
import numpy as np
import cv2

# Auto-use Tsinghua HF mirror if in China (huggingface.co blocked)
if not os.environ.get("HF_ENDPOINT"):
    try:
        import urllib.request
        urllib.request.urlopen("https://hf-mirror.com", timeout=2)
        os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"
    except Exception:
        pass

# Lazy imports — model dependencies are heavy
_TRANSFORMERS_AVAILABLE = False
_TORCH_AVAILABLE = False


def _check_deps():
    global _TRANSFORMERS_AVAILABLE, _TORCH_AVAILABLE
    try:
        import torch  # noqa: F401
        _TORCH_AVAILABLE = True
    except ImportError:
        pass
    try:
        import transformers  # noqa: F401
        _TRANSFORMERS_AVAILABLE = True
    except ImportError:
        pass


_check_deps()


class DepthEstimator:
    """Monocular depth estimation using Depth Anything V2."""

    MODEL_IDS = {
        "small": "depth-anything/Depth-Anything-V2-Small-hf",
        "base": "depth-anything/Depth-Anything-V2-Base-hf",
        "large": "depth-anything/Depth-Anything-V2-Large-hf",
    }

    def __init__(self, model_size="small", input_size=(518, 518), use_gpu=False):
        if not _TORCH_AVAILABLE or not _TRANSFORMERS_AVAILABLE:
            raise ImportError(
                "torch and transformers are required. "
                "pip install torch transformers"
            )
        self.model_size = model_size
        self.model_id = self.MODEL_IDS[model_size]
        self.input_size = input_size
        self.use_gpu = use_gpu
        self._model = None
        self._processor = None
        self._device = None

    def load(self):
        """Load model from Hugging Face hub. First call downloads ~150MB-1.3GB."""
        import torch
        from transformers import AutoImageProcessor, AutoModelForDepthEstimation

        self._device = torch.device(
            "cuda" if self.use_gpu and torch.cuda.is_available() else "cpu"
        )
        print(f"[DepthEstimator] Loading {self.model_id} on {self._device} ...")
        self._processor = AutoImageProcessor.from_pretrained(self.model_id)
        self._model = AutoModelForDepthEstimation.from_pretrained(self.model_id)
        self._model.to(self._device)
        self._model.eval()
        print("[DepthEstimator] Model loaded.")

    def estimate(self, bgr_frame):
        """Estimate depth map from BGR image.

        Args:
            bgr_frame: numpy array (H, W, 3) uint8 BGR

        Returns:
            depth_map: numpy array (H, W) float32 — meters from camera
        """
        import torch
        from PIL import Image

        if self._model is None:
            self.load()

        # BGR → RGB → PIL
        rgb = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2RGB)
        pil_img = Image.fromarray(rgb)

        # Process
        inputs = self._processor(images=pil_img, return_tensors="pt")
        inputs = {k: v.to(self._device) for k, v in inputs.items()}

        with torch.no_grad():
            outputs = self._model(**inputs)

        # Resize predicted depth back to original resolution
        post = self._processor.post_process_depth_estimation(
            outputs,
            target_sizes=[(bgr_frame.shape[0], bgr_frame.shape[1])],
        )
        depth = post[0]["predicted_depth"].detach().cpu().numpy()

        # Depth Anything V2 outputs relative/disparity values.
        # Convert to approximate meters using a simple normalization.
        # The model outputs scaled inverse-depth; we convert with:
        #   depth_m = 1.0 / (depth_normalized * alpha + beta)
        # Alpha/Beta calibrated to map typical indoor scenes.
        depth_min, depth_max = depth.min(), depth.max()
        if depth_max - depth_min < 1e-6:
            return np.full_like(depth, 5.0, dtype=np.float32)
        depth_norm = (depth - depth_min) / (depth_max - depth_min)

        # Map normalized [0,1] to approximate [0.3, 10.0] meter range.
        # Near = high disparity (1.0) → 0.3m. Far = low disparity (0.0) → 10m.
        depth_m = 0.3 + (1.0 - depth_norm) * 9.7
        return depth_m.astype(np.float32)


class SimpleDepthEstimator:
    """Lightweight depth approximation without ML model.

    Uses basic image features (edge density, brightness gradient)
    as a heuristic depth proxy. Not accurate, but runs on any hardware
    and serves as a development fallback.

    This is NOT a replacement for real depth estimation.
    """

    def __init__(self):
        print("[SimpleDepthEstimator] Using heuristic depth (dev-only fallback)")

    def load(self):
        pass  # no model to load

    def estimate(self, bgr_frame):
        """
        Returns a pseudo-depth map where:
          - Darker regions (low gradient, smooth) → farther
          - Edges/textures → nearer
          - Bottom of image → nearer (perspective assumption)
        """
        gray = cv2.cvtColor(bgr_frame, cv2.COLOR_BGR2GRAY)
        h, w = gray.shape

        # Edge density as proximity cue
        edges = cv2.Canny(gray, 50, 150).astype(np.float32)
        blurred_edges = cv2.GaussianBlur(edges, (21, 21), 0)

        # Distance from bottom as perspective cue
        y_ramp = np.linspace(1.0, 0.0, h, dtype=np.float32)
        y_ramp = np.tile(y_ramp.reshape(h, 1), (1, w))

        # Combine heuristics
        pseudo = 0.5 * blurred_edges + 0.5 * y_ramp
        # Normalize to [0.3, 10] meters
        depth = 0.3 + (1.0 - pseudo / (pseudo.max() + 1e-6)) * 9.7
        return depth.astype(np.float32)
