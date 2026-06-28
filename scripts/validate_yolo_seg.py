from __future__ import annotations

import argparse
from pathlib import Path

from ultralytics import YOLO


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate a trained Ultralytics YOLO segmentation model.")
    parser.add_argument("--weights", type=Path, required=True, help="Path to a trained .pt checkpoint.")
    parser.add_argument("--data", type=Path, default=Path("prepared") / "welding_yolo_seg" / "dataset.yaml")
    parser.add_argument("--split", default="test", choices=["val", "test"])
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--device", default="0")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    model = YOLO(str(args.weights.resolve()))
    metrics = model.val(
        data=str(args.data.resolve()),
        split=args.split,
        imgsz=args.imgsz,
        device=args.device,
        task="segment",
        plots=True,
    )
    print("Validation summary:")
    for key, value in metrics.results_dict.items():
        print(f"  {key}: {value}")

    print("Per-class mask mAP50-95:")
    for class_index, score in enumerate(metrics.maps):
        class_name = metrics.names[class_index]
        print(f"  {class_name}: {score}")


if __name__ == "__main__":
    main()
