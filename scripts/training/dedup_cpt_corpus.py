#!/usr/bin/env python3
"""
既存の cpt_corpus.txt に方案A(保守的)の重複除去を適用する。

除去対象:
  1. 完全重複 (MD5 hash 一致) — 最初の1件のみ保持
  2. LOW価値ボイラープレート — 색인/索引, 注意事項

Usage:
    # ドライラン (統計のみ)
    python scripts/training/dedup_cpt_corpus.py --dry-run

    # 実行 (新しいファイルに出力)
    python scripts/training/dedup_cpt_corpus.py

    # カスタム入出力
    python scripts/training/dedup_cpt_corpus.py \
        --input dataset_pipeline/output/cpt_corpus.txt \
        --output dataset_pipeline/output/cpt_corpus_dedup.txt
"""

import argparse
import hashlib
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

SEPARATOR = "<|endoftext|>"

# 方案A: LOW価値ボイラープレートのセクション名キーワード
BOILERPLATE_SECTIONS = [
    "색인",       # Korean index pages
    "索引",       # Japanese index pages
    "注意事項",   # Notices / disclaimers
]


def dedup(input_path: Path, output_path: Path, dry_run: bool = False) -> dict:
    text = input_path.read_text(encoding="utf-8")
    raw_docs = text.split(SEPARATOR)
    docs = [(i, d.strip()) for i, d in enumerate(raw_docs) if d.strip()]

    stats = {
        "input_docs": len(docs),
        "exact_removed": 0,
        "boilerplate_removed": 0,
        "exact_removed_products": {},
        "boilerplate_removed_sections": {},
        "output_docs": 0,
    }

    # Step 1: 完全重複除去
    seen_hashes: dict[str, int] = {}
    after_exact: list[tuple[int, str]] = []
    for idx, doc in docs:
        h = hashlib.md5(doc.encode("utf-8")).hexdigest()
        if h in seen_hashes:
            stats["exact_removed"] += 1
            first_line = doc.split("\n", 1)[0]
            product = first_line.split(" — ")[0].lstrip("# ").strip() if " — " in first_line else "unknown"
            stats["exact_removed_products"][product] = stats["exact_removed_products"].get(product, 0) + 1
        else:
            seen_hashes[h] = idx
            after_exact.append((idx, doc))

    # Step 2: ボイラープレート除去
    kept: list[str] = []
    for idx, doc in after_exact:
        first_line = doc.split("\n", 1)[0]
        section = first_line.rsplit(" — ", 1)[-1] if " — " in first_line else ""

        # 完全一致のみ (部分一致だと "注意事項とリターンコード" 等の技術文書も除去してしまう)
        is_boilerplate = section in BOILERPLATE_SECTIONS
        if is_boilerplate:
            stats["boilerplate_removed"] += 1
            stats["boilerplate_removed_sections"][section] = (
                stats["boilerplate_removed_sections"].get(section, 0) + 1
            )
            continue

        kept.append(doc)

    stats["output_docs"] = len(kept)

    if not dry_run:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            for i, doc in enumerate(kept):
                f.write(doc)
                if i < len(kept) - 1:
                    f.write(f"\n{SEPARATOR}\n")
        file_size = output_path.stat().st_size
        print(f"Wrote {output_path} ({file_size / 1024 / 1024:.1f} MB)")

    return stats


def main():
    parser = argparse.ArgumentParser(description="CPT corpus dedup (方案A)")
    parser.add_argument(
        "--input",
        default="dataset_pipeline/output/cpt_corpus.txt",
        help="入力ファイルパス",
    )
    parser.add_argument(
        "--output",
        default="dataset_pipeline/output/cpt_corpus_dedup.txt",
        help="出力ファイルパス",
    )
    parser.add_argument("--dry-run", action="store_true", help="統計のみ表示")
    args = parser.parse_args()

    input_path = Path(args.input)
    output_path = Path(args.output)

    if not input_path.exists():
        print(f"ERROR: {input_path} not found")
        sys.exit(1)

    stats = dedup(input_path, output_path, dry_run=args.dry_run)

    total_removed = stats["exact_removed"] + stats["boilerplate_removed"]
    print("\n=== CPT Dedup Results (方案A: 保守的) ===")
    print(f"  Input:  {stats['input_docs']} docs")
    print(f"  Output: {stats['output_docs']} docs")
    print(f"  Removed: {total_removed} ({total_removed * 100 / max(stats['input_docs'], 1):.1f}%)")
    print(f"    - Exact duplicates: {stats['exact_removed']}")
    print(f"    - Boilerplate:      {stats['boilerplate_removed']}")

    if stats["exact_removed_products"]:
        print("\n  Exact duplicates by product:")
        for product, count in sorted(stats["exact_removed_products"].items(), key=lambda x: -x[1]):
            print(f"    {product:35s} {count}")

    if stats["boilerplate_removed_sections"]:
        print("\n  Boilerplate by section:")
        for section, count in sorted(stats["boilerplate_removed_sections"].items(), key=lambda x: -x[1]):
            print(f"    {section:35s} {count}")

    if args.dry_run:
        print("\n(Dry run — no files written)")


if __name__ == "__main__":
    main()
