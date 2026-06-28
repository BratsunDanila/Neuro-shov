from __future__ import annotations

import argparse
from pathlib import Path

import torch
from ultralytics import YOLO


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Train an Ultralytics YOLO instance-segmentation model.")
    parser.add_argument("--data", type=Path, default=Path("prepared") / "welding_yolo_seg" / "dataset.yaml")
    parser.add_argument("--model", default="yolo26s-seg.pt", help="Segmentation checkpoint to fine-tune.")
    parser.add_argument("--epochs", type=int, default=120)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--batch", type=int, default=8)
    parser.add_argument("--device", default="0" if torch.cuda.is_available() else "cpu")
    parser.add_argument("--project", type=Path, default=Path("runs"))
    parser.add_argument("--name", default="welding-seg-yolo26s")
    parser.add_argument("--patience", type=int, default=30)
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--cache", default="ram", choices=["ram", "disk", "False"])
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    model = YOLO(args.model)
    cache = False if args.cache == "False" else args.cache

    model.train(
        data=str(args.data.resolve()),
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        project=str(args.project.resolve()),
        name=args.name,
        patience=args.patience,
        workers=args.workers,
        seed=args.seed,
        cache=cache,
        task="segment",
        exist_ok=True,
        pretrained=True,
        plots=True,
        close_mosaic=10,
        amp=True,
    )


if __name__ == "__main__":
    main()
