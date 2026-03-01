#!/usr/bin/env python3
"""
CPT corpus を ms-swift 'swift pt' 互換 JSONL 形式に変換するスクリプト。

ms-swift CPT フォーマット:
  {"messages": [{"role": "assistant", "content": "テキスト内容"}]}

Usage:
    python scripts/training/convert_cpt_to_swift.py \
        --input dataset_pipeline/output/cpt_corpus.txt \
        --output dataset_pipeline/output/cpt_swift.jsonl

    # 統計のみ (ドライラン)
    python scripts/training/convert_cpt_to_swift.py \
        --input dataset_pipeline/output/cpt_corpus.txt --dry-run
"""

import argparse
import json
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

SEPARATOR = "<|endoftext|>"


def convert(input_path: Path, output_path: Path, dry_run: bool = False) -> dict:
    """Plain text CPT corpus → ms-swift JSONL 変換."""
    text = input_path.read_text(encoding="utf-8")
    documents = text.split(SEPARATOR)

    stats = {
        "total_documents": 0,
        "skipped_empty": 0,
        "written": 0,
        "total_chars": 0,
        "min_chars": float("inf"),
        "max_chars": 0,
        "by_product": {},
    }

    records = []
    for doc in documents:
        doc = doc.strip()
        if not doc:
            stats["skipped_empty"] += 1
            continue

        stats["total_documents"] += 1
        char_len = len(doc)
        stats["total_chars"] += char_len
        stats["min_chars"] = min(stats["min_chars"], char_len)
        stats["max_chars"] = max(stats["max_chars"], char_len)

        # 製品名抽出 (ヘッダ: "# Product — Manual — Section")
        first_line = doc.split("\n", 1)[0]
        if first_line.startswith("# ") and " — " in first_line:
            product = first_line.split(" — ")[0].lstrip("# ").strip()
            stats["by_product"][product] = stats["by_product"].get(product, 0) + 1

        record = {"messages": [{"role": "assistant", "content": doc}]}
        records.append(record)

    stats["written"] = len(records)
    if stats["total_documents"] > 0:
        stats["avg_chars"] = stats["total_chars"] // stats["total_documents"]
    else:
        stats["avg_chars"] = 0
    if stats["min_chars"] == float("inf"):
        stats["min_chars"] = 0

    if not dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        print(f"Wrote {len(records)} records to {output_path}")

    return stats


def main():
    parser = argparse.ArgumentParser(
        description="CPT corpus → ms-swift JSONL 変換",
    )
    parser.add_argument(
        "--input",
        default="dataset_pipeline/output/cpt_corpus.txt",
        help="入力 CPT corpus パス",
    )
    parser.add_argument(
        "--output",
        default="dataset_pipeline/output/cpt_swift.jsonl",
        help="出力 JSONL パス",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="統計のみ表示 (ファイル書き出しなし)",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"ERROR: 入力ファイルが見つかりません: {input_path}")
        sys.exit(1)

    stats = convert(input_path, output_path, dry_run=args.dry_run)

    print("\n=== Conversion Stats ===")
    print(f"  Total documents: {stats['total_documents']}")
    print(f"  Skipped empty:   {stats['skipped_empty']}")
    print(f"  Written records:  {stats['written']}")
    print(f"  Total chars:      {stats['total_chars']:,}")
    print(f"  Avg chars/doc:    {stats['avg_chars']:,}")
    print(f"  Min/Max chars:    {stats['min_chars']:,} / {stats['max_chars']:,}")

    if stats["by_product"]:
        print("\n  By Product (top 15):")
        sorted_products = sorted(
            stats["by_product"].items(), key=lambda x: x[1], reverse=True
        )
        for product, count in sorted_products[:15]:
            print(f"    {product:35s} {count:6d}")

    if args.dry_run:
        print("\n(Dry run — no files written)")


if __name__ == "__main__":
    main()
