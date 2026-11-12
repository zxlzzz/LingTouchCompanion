"""Regenerate the Android YOLOv8s-seg ONNX from the original local checkpoint."""
import argparse
import hashlib
import os
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--weights', required=True, type=Path)
    args = parser.parse_args()
    weights = args.weights.resolve()
    if hashlib.sha256(weights.read_bytes()).hexdigest() != '0bac0770b55e5eb5b76a61bc535673288dcec36c2bc0cd25ee0d584c632f3413':
        parser.error('The original YOLOv8s-seg checkpoint SHA-256 differs')
    work = ROOT/'.build/vision/exported-yolo'
    work.mkdir(parents=True, exist_ok=True)
    os.environ.update(YOLO_CONFIG_DIR=str(work/'settings'), YOLO_AUTOINSTALL='false',
                      YOLO_OFFLINE='true', MPLCONFIGDIR=str(work/'mpl'))
    import onnx
    import torch
    from ultralytics import YOLO, settings
    torch.set_num_threads(3)
    settings.update({'sync': False})
    checkpoint = shutil.copyfile(weights,work/'yolov8s-seg.pt')
    model = YOLO(checkpoint)
    export = Path(model.export(format='onnx',imgsz=[384,640],opset=17,simplify=False,
                               dynamic=False,nms=False,device='cpu'))
    graph = onnx.load(export)
    onnx.checker.check_model(graph)
    print(export, hashlib.sha256(export.read_bytes()).hexdigest())

if __name__ == '__main__':
    main()
