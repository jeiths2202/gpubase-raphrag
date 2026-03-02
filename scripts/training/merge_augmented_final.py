#!/usr/bin/env python3
"""
Merge augmented data back with original v5_final structure
and generate final train/eval splits.
"""

import json
import random
from pathlib import Path
from typing import Dict, List
from collections import defaultdict

# Paths
BASE_DIR = Path(__file__).parent.parent.parent
SUMMARIES_DIR = BASE_DIR / "uploads" / "summaries"
V5_FINAL_DIR = SUMMARIES_DIR / "multi_lora_v5_final"
V5_AUGMENTED_V2_DIR = SUMMARIES_DIR / "multi_lora_v5_augmented_v2"
OUTPUT_DIR = SUMMARIES_DIR / "multi_lora_v6_final"

# Train/Eval split ratio
TRAIN_RATIO = 0.8


def load_data(directory: Path) -> Dict[str, List]:
    """Load all product data from a directory."""
    data = {}
    for product_dir in directory.iterdir():
        if not product_dir.is_dir():
            continue
        train_file = product_dir / "train.json"
        if train_file.exists():
            with open(train_file, "r", encoding="utf-8") as f:
                data[product_dir.name] = json.load(f)
    return data


def main():
    print("[START] Merging Augmented Data to v6_final")
    print("=" * 60)

    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # Load augmented data
    augmented_data = load_data(V5_AUGMENTED_V2_DIR)

    stats = {
        "summary": {
            "total_records": 0,
            "total_train": 0,
            "total_eval": 0,
            "products": 0,
        },
        "products": {},
    }

    all_train = []
    all_eval = []

    for product, items in sorted(augmented_data.items()):
        total = len(items)

        # Shuffle for random split
        random.seed(42)  # Reproducibility
        random.shuffle(items)

        # Split train/eval
        split_idx = int(total * TRAIN_RATIO)
        train_items = items[:split_idx]
        eval_items = items[split_idx:]

        # Save product-specific files
        product_dir = OUTPUT_DIR / product
        product_dir.mkdir(parents=True, exist_ok=True)

        with open(product_dir / "train.json", "w", encoding="utf-8") as f:
            json.dump(train_items, f, ensure_ascii=False, indent=2)

        with open(product_dir / "eval.json", "w", encoding="utf-8") as f:
            json.dump(eval_items, f, ensure_ascii=False, indent=2)

        all_train.extend(train_items)
        all_eval.extend(eval_items)

        stats["products"][product] = {
            "total": total,
            "train": len(train_items),
            "eval": len(eval_items),
        }

        status = "[OK]" if total >= 50 else "[LOW]"
        print(f"  {status} {product}: {total} (train: {len(train_items)}, eval: {len(eval_items)})")

        stats["summary"]["total_records"] += total
        stats["summary"]["products"] += 1

    stats["summary"]["total_train"] = len(all_train)
    stats["summary"]["total_eval"] = len(all_eval)

    # Save combined files
    with open(OUTPUT_DIR / "train_all.json", "w", encoding="utf-8") as f:
        json.dump(all_train, f, ensure_ascii=False, indent=2)

    with open(OUTPUT_DIR / "eval_all.json", "w", encoding="utf-8") as f:
        json.dump(all_eval, f, ensure_ascii=False, indent=2)

    # Save stats
    with open(OUTPUT_DIR / "merge_stats.json", "w", encoding="utf-8") as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print("[REPORT] Final Merge Summary")
    print("=" * 60)
    print(f"Total Products: {stats['summary']['products']}")
    print(f"Total Records: {stats['summary']['total_records']}")
    print(f"Train Records: {stats['summary']['total_train']}")
    print(f"Eval Records: {stats['summary']['total_eval']}")
    print(f"\nOutput: {OUTPUT_DIR}")
    print("[DONE] Merge complete!")


if __name__ == "__main__":
    main()
