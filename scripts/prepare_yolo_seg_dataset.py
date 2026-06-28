from __future__ import annotations

import argparse
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np
import yaml
from ultralytics.data.converter import merge_multi_segment


SPLIT_MAP = {"train": "train", "valid": "val", "test": "test"}


def load_coco(json_path: Path) -> dict:
    with json_path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def normalize_segments(segmentation: list, width: int, height: int) -> list[float]:
    if not segmentation:
        return []

    if len(segmentation) > 1:
        merged = merge_multi_segment(segmentation)
        points = (np.concatenate(merged, axis=0) / np.array([width, height])).reshape(-1).tolist()
    else:
        points = (
            np.array(segmentation[0], dtype=np.float64).reshape(-1, 2) / np.array([width, height], dtype=np.float64)
        ).reshape(-1).tolist()

    return [min(max(value, 0.0), 1.0) for value in points]


def write_label_file(label_path: Path, lines: list[str]) -> None:
    label_path.parent.mkdir(parents=True, exist_ok=True)
    with label_path.open("w", encoding="utf-8") as handle:
        if lines:
            handle.write("\n".join(lines) + "\n")


def prepare_dataset(source_root: Path, output_root: Path) -> dict:
    raw_splits: dict[str, dict] = {}
    global_category_counts: Counter[str] = Counter()

    for split_name in SPLIT_MAP:
        json_path = source_root / split_name / "_annotations.coco.json"
        data = load_coco(json_path)
        raw_splits[split_name] = data
        categories = {item["id"]: item["name"] for item in data["categories"]}
        for annotation in data["annotations"]:
            global_category_counts[categories[annotation["category_id"]]] += 1

    active_categories: list[dict] = []
    removed_categories: list[str] = []
    original_categories = raw_splits["train"]["categories"]
    for category in original_categories:
        if global_category_counts[category["name"]] > 0:
            active_categories.append(category)
        else:
            removed_categories.append(category["name"])

    old_id_to_new_coco_id = {cat["id"]: idx + 1 for idx, cat in enumerate(active_categories)}
    old_id_to_yolo_id = {cat["id"]: idx for idx, cat in enumerate(active_categories)}
    old_id_to_name = {cat["id"]: cat["name"] for cat in active_categories}
    active_category_names = [cat["name"] for cat in active_categories]

    if output_root.exists():
        shutil.rmtree(output_root)

    summary: dict[str, object] = {
        "source_root": str(source_root.resolve()),
        "output_root": str(output_root.resolve()),
        "removed_categories": removed_categories,
        "class_names": active_category_names,
        "splits": {},
    }

    for split_name, yolo_split in SPLIT_MAP.items():
        split_root = source_root / split_name
        image_dir = output_root / "images" / yolo_split
        label_dir = output_root / "labels" / yolo_split
        coco_dir = output_root / "coco"
        image_dir.mkdir(parents=True, exist_ok=True)
        label_dir.mkdir(parents=True, exist_ok=True)
        coco_dir.mkdir(parents=True, exist_ok=True)

        data = raw_splits[split_name]
        images = data["images"]
        annotations = data["annotations"]
        image_by_id = {item["id"]: item for item in images}
        annotations_by_image: dict[int, list[dict]] = defaultdict(list)
        split_category_counts: Counter[str] = Counter()

        cleaned_annotations: list[dict] = []
        new_annotation_id = 1
        for annotation in annotations:
            if annotation["category_id"] not in old_id_to_new_coco_id:
                continue
            category_name = old_id_to_name[annotation["category_id"]]
            split_category_counts[category_name] += 1
            cleaned = dict(annotation)
            cleaned["id"] = new_annotation_id
            cleaned["category_id"] = old_id_to_new_coco_id[annotation["category_id"]]
            cleaned_annotations.append(cleaned)
            annotations_by_image[annotation["image_id"]].append(annotation)
            new_annotation_id += 1

        for image in images:
            src_image = split_root / image["file_name"]
            dst_image = image_dir / image["file_name"]
            if not src_image.exists():
                raise FileNotFoundError(f"Missing image referenced in annotations: {src_image}")
            shutil.copy2(src_image, dst_image)

            label_lines: list[str] = []
            for annotation in annotations_by_image.get(image["id"], []):
                if annotation["category_id"] not in old_id_to_yolo_id:
                    continue

                segment = normalize_segments(annotation.get("segmentation", []), image["width"], image["height"])
                if len(segment) < 6:
                    continue

                cls_id = old_id_to_yolo_id[annotation["category_id"]]
                label_lines.append(" ".join([str(cls_id), *[f"{value:.6f}" for value in segment]]))

            deduped_lines = list(dict.fromkeys(label_lines))
            write_label_file((label_dir / image["file_name"]).with_suffix(".txt"), deduped_lines)

        cleaned_categories = [
            {"id": idx + 1, "name": name, "supercategory": "none"} for idx, name in enumerate(active_category_names)
        ]
        cleaned_coco = {
            "licenses": data.get("licenses", []),
            "info": data.get("info", {}),
            "images": images,
            "annotations": cleaned_annotations,
            "categories": cleaned_categories,
        }
        with (coco_dir / f"{yolo_split}.json").open("w", encoding="utf-8") as handle:
            json.dump(cleaned_coco, handle, ensure_ascii=False, indent=2)

        summary["splits"][yolo_split] = {
            "images": len(images),
            "annotations": len(cleaned_annotations),
            "category_counts": dict(split_category_counts),
        }

    dataset_yaml = {
        "path": str(output_root.resolve()),
        "train": "images/train",
        "val": "images/val",
        "test": "images/test",
        "names": {idx: name for idx, name in enumerate(active_category_names)},
    }
    with (output_root / "dataset.yaml").open("w", encoding="utf-8") as handle:
        yaml.safe_dump(dataset_yaml, handle, allow_unicode=True, sort_keys=False)

    with (output_root / "summary.json").open("w", encoding="utf-8") as handle:
        json.dump(summary, handle, ensure_ascii=False, indent=2)

    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare the welding dataset for Ultralytics YOLO segmentation.")
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("Dataset"),
        help="Path to the original Roboflow-exported COCO dataset.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("prepared") / "welding_yolo_seg",
        help="Where to write the cleaned dataset in YOLO segmentation format.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = prepare_dataset(args.source.resolve(), args.output.resolve())
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
