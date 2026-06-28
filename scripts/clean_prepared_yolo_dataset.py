from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from collections import Counter, defaultdict
from pathlib import Path

import yaml


SPLITS = ["train", "val", "test"]
SPLIT_PRIORITY = {"train": 0, "val": 1, "test": 2}


def md5(path: Path) -> str:
    return hashlib.md5(path.read_bytes()).hexdigest()


def read_label_lines(path: Path) -> list[str]:
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def write_label_lines(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = "\n".join(lines)
    if text:
        text += "\n"
    path.write_text(text, encoding="utf-8")


def choose_canonical(items: list[dict]) -> dict:
    return sorted(items, key=lambda item: (SPLIT_PRIORITY[item["split"]], item["image"].name))[0]


def build_duplicate_groups(source_root: Path) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for split in SPLITS:
        image_dir = source_root / "images" / split
        label_dir = source_root / "labels" / split
        for image_path in image_dir.glob("*.jpg"):
            label_path = label_dir / image_path.with_suffix(".txt").name
            groups[md5(image_path)].append(
                {
                    "split": split,
                    "image": image_path,
                    "label": label_path,
                }
            )
    return groups


def clean_dataset(source_root: Path, output_root: Path) -> dict:
    if output_root.exists():
        shutil.rmtree(output_root)

    for split in SPLITS:
        (output_root / "images" / split).mkdir(parents=True, exist_ok=True)
        (output_root / "labels" / split).mkdir(parents=True, exist_ok=True)

    groups = build_duplicate_groups(source_root)

    summary: dict[str, object] = {
        "source_root": str(source_root.resolve()),
        "output_root": str(output_root.resolve()),
        "cross_split_duplicate_groups": 0,
        "within_split_duplicate_groups": 0,
        "removed_files": [],
        "merged_within_split": [],
        "kept_files": [],
    }

    kept_records: list[tuple[str, str]] = []

    for hash_value, items in groups.items():
        canonical = choose_canonical(items)
        split_set = {item["split"] for item in items}

        if len(items) > 1:
            if len(split_set) > 1:
                summary["cross_split_duplicate_groups"] += 1
            else:
                summary["within_split_duplicate_groups"] += 1

        canonical_output_image = output_root / "images" / canonical["split"] / canonical["image"].name
        canonical_output_label = output_root / "labels" / canonical["split"] / canonical["label"].name

        if len(items) == 1:
            shutil.copy2(canonical["image"], canonical_output_image)
            shutil.copy2(canonical["label"], canonical_output_label)
            kept_records.append((canonical["split"], canonical["image"].name))
            continue

        same_split_items = [item for item in items if item["split"] == canonical["split"]]
        label_lines = read_label_lines(canonical["label"])

        # Merge exact duplicate images only inside the same split.
        if len(same_split_items) > 1:
            merged_lines: list[str] = []
            for item in sorted(same_split_items, key=lambda x: x["image"].name):
                merged_lines.extend(read_label_lines(item["label"]))
            merged_lines = list(dict.fromkeys(merged_lines))
            label_lines = merged_lines
            summary["merged_within_split"].append(
                {
                    "split": canonical["split"],
                    "kept": canonical["image"].name,
                    "merged_count": len(same_split_items),
                    "hash": hash_value,
                }
            )

        shutil.copy2(canonical["image"], canonical_output_image)
        write_label_lines(canonical_output_label, label_lines)
        kept_records.append((canonical["split"], canonical["image"].name))
        summary["kept_files"].append(
            {
                "split": canonical["split"],
                "image": canonical["image"].name,
                "hash": hash_value,
                "group_size": len(items),
            }
        )

        for item in items:
            if item["image"] == canonical["image"] and item["split"] == canonical["split"]:
                continue
            summary["removed_files"].append(
                {
                    "split": item["split"],
                    "image": item["image"].name,
                    "hash": hash_value,
                    "reason": "cross_split_duplicate_removed"
                    if item["split"] != canonical["split"]
                    else "within_split_duplicate_merged",
                }
            )

    dataset_yaml = yaml.safe_load((source_root / "dataset.yaml").read_text(encoding="utf-8"))
    dataset_yaml["path"] = str(output_root.resolve())
    (output_root / "dataset.yaml").write_text(
        yaml.safe_dump(dataset_yaml, allow_unicode=True, sort_keys=False),
        encoding="utf-8",
    )

    split_counts = {}
    for split in SPLITS:
        images = list((output_root / "images" / split).glob("*.jpg"))
        labels = list((output_root / "labels" / split).glob("*.txt"))
        split_counts[split] = {"images": len(images), "labels": len(labels)}
    summary["split_counts"] = split_counts

    (output_root / "cleaning_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return summary


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Clean a prepared YOLO segmentation dataset from exact image duplicates.")
    parser.add_argument(
        "--source",
        type=Path,
        default=Path("prepared") / "welding_yolo_seg",
        help="Path to the prepared YOLO segmentation dataset.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("prepared") / "welding_yolo_seg_clean",
        help="Output path for the cleaned dataset.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    summary = clean_dataset(args.source.resolve(), args.output.resolve())
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
