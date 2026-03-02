#!/usr/bin/env python3
"""
Paraphrase Augmentation Script

Generates additional Q&A pairs by paraphrasing existing questions
for products with insufficient data.
"""

import json
import re
import random
from pathlib import Path
from typing import Dict, List, Tuple
from collections import defaultdict

# Paths
BASE_DIR = Path(__file__).parent.parent.parent
SUMMARIES_DIR = BASE_DIR / "uploads" / "summaries"
V5_AUGMENTED_DIR = SUMMARIES_DIR / "multi_lora_v5_augmented"
OUTPUT_DIR = SUMMARIES_DIR / "multi_lora_v5_augmented_v2"

# Products that still need augmentation
PRODUCTS_NEED_MORE = {
    "openframe_ndb_v2": 100,
    "prosort_v2": 100,
    "prosync_v2": 100,
    "ofasm_v2": 100,
    "protrieve_v2": 100,
    "ofstudio_v2": 100,
    "openframe_hidb_v2": 100,
    "ofminer_v2": 100,
    "openframe_osi_v2": 100,
    "openframe_tacf_v2": 100,
    "ofmanager_v2": 100,
    "openframe_aim_v2": 100,
    "ofpli_v2": 100,
}

# Question paraphrase patterns
PARAPHRASE_PATTERNS = [
    # What is X?
    (r"(.+)とは何ですか[？?]", [
        "{0}について教えてください。",
        "{0}の概念を説明してください。",
        "{0}の意味は何ですか？",
        "{0}について詳しく教えてください。",
        "{0}はどのようなものですか？",
    ]),
    # Explain X
    (r"(.+)について説明してください[。.]?", [
        "{0}とは何ですか？",
        "{0}の詳細を教えてください。",
        "{0}について教えてください。",
        "{0}の概念を説明してください。",
    ]),
    # How to X?
    (r"(.+)の(使い方|やり方|方法|手順)を教えてください[。.]?", [
        "{0}の{1}を説明してください。",
        "{0}はどのように{1_verb}しますか？",
        "{0}を{1_verb}するにはどうすればいいですか？",
        "{0}の{1}について教えてください。",
    ]),
    # Error code
    (r"エラー(コード)?[-_]?(\d+)(.+)", [
        "エラー{1}の原因を教えてください。",
        "エラーコード{1}の解決方法は？",
        "{1}エラーが出た時の対処法を教えてください。",
    ]),
    # Command
    (r"(.+)コマンド(.+)", [
        "{0}コマンドについて説明してください。",
        "{0}の使い方を教えてください。",
        "{0}コマンドの構文を教えてください。",
    ]),
    # Configuration
    (r"(.+)(パラメータ|設定|オプション)(.+)", [
        "{0}{1}について説明してください。",
        "{0}{1}の詳細を教えてください。",
        "{0}{1}の設定方法は？",
    ]),
]

# Product-specific context phrases to add diversity
PRODUCT_CONTEXT = {
    "openframe_ndb_v2": ["NDB", "Network Database", "階層型データベース", "ネットワークデータベース"],
    "openframe_hidb_v2": ["HIDB", "Hierarchical Database", "階層型DB", "IMS互換"],
    "prosort_v2": ["ProSort", "ソート", "並べ替え", "ソートユーティリティ"],
    "prosync_v2": ["ProSync", "同期", "データ同期", "ファイル同期"],
    "protrieve_v2": ["ProTrieve", "検索", "データ検索", "高速検索"],
    "ofasm_v2": ["OFAsm", "アセンブラ", "アセンブリ", "HLASM互換"],
    "ofstudio_v2": ["OFStudio", "開発ツール", "IDE", "統合開発環境"],
    "openframe_osi_v2": ["OSI", "オンライン", "CICS互換", "トランザクション処理"],
    "ofminer_v2": ["OFMiner", "分析", "マイグレーション分析", "資産分析"],
    "openframe_tacf_v2": ["TACF", "セキュリティ", "アクセス制御", "認証"],
    "ofmanager_v2": ["OFManager", "管理ツール", "運用管理", "システム管理"],
    "openframe_aim_v2": ["AIM", "アプリケーション", "アプリ管理", "AP管理"],
    "ofpli_v2": ["OFPli", "PL/I", "プログラム言語", "コンパイラ"],
}


def extract_qa_from_chatml(text: str) -> Tuple[str, str, str]:
    """Extract question, answer, and system from ChatML format."""
    system_match = re.search(r"<\|im_start\|>system\n(.+?)<\|im_end\|>", text, re.DOTALL)
    user_match = re.search(r"<\|im_start\|>user\n(.+?)<\|im_end\|>", text, re.DOTALL)
    assistant_match = re.search(r"<\|im_start\|>assistant\n(.+?)<\|im_end\|>", text, re.DOTALL)

    system = system_match.group(1).strip() if system_match else ""
    question = user_match.group(1).strip() if user_match else ""
    answer = assistant_match.group(1).strip() if assistant_match else ""

    return system, question, answer


def format_chatml(system: str, question: str, answer: str) -> str:
    """Format as ChatML."""
    return f"""<|im_start|>system
{system}<|im_end|>
<|im_start|>user
{question}<|im_end|>
<|im_start|>assistant
{answer}<|im_end|>"""


def paraphrase_question(question: str, product: str) -> List[str]:
    """Generate paraphrased versions of a question."""
    paraphrases = []

    for pattern, templates in PARAPHRASE_PATTERNS:
        match = re.match(pattern, question)
        if match:
            groups = match.groups()
            for template in templates:
                try:
                    # Handle verb transformation
                    template_filled = template
                    if "{1_verb}" in template and len(groups) > 1:
                        verb_map = {
                            "使い方": "使用",
                            "やり方": "実行",
                            "方法": "行う",
                            "手順": "進める",
                        }
                        verb = verb_map.get(groups[1], groups[1])
                        template_filled = template_filled.replace("{1_verb}", verb)

                    # Format with groups
                    for i, g in enumerate(groups):
                        template_filled = template_filled.replace(f"{{{i}}}", g or "")

                    if template_filled != question:
                        paraphrases.append(template_filled)
                except Exception:
                    continue
            break

    # Add product-specific variations if still not enough
    if len(paraphrases) < 3 and product in PRODUCT_CONTEXT:
        contexts = PRODUCT_CONTEXT[product]
        for ctx in contexts[:2]:
            if ctx.lower() not in question.lower():
                # Add context to question
                new_q = f"{ctx}の{question}"
                if new_q not in paraphrases:
                    paraphrases.append(new_q)

    return paraphrases[:3]  # Limit to 3 paraphrases


def generate_synthetic_qa(product: str, existing_qa: List[Dict], target: int) -> List[Dict]:
    """Generate synthetic Q&A pairs from existing data."""
    current = len(existing_qa)
    needed = max(0, target - current)

    if needed == 0 or current == 0:
        return []

    new_items = []
    existing_questions = set()

    for item in existing_qa:
        _, q, _ = extract_qa_from_chatml(item.get("text", ""))
        existing_questions.add(q)

    # Generate paraphrases from existing items
    for item in existing_qa:
        if len(new_items) >= needed:
            break

        system, question, answer = extract_qa_from_chatml(item.get("text", ""))
        if not question or not answer:
            continue

        paraphrases = paraphrase_question(question, product)
        for para_q in paraphrases:
            if len(new_items) >= needed:
                break
            if para_q not in existing_questions and len(para_q) > 10:
                new_chatml = format_chatml(system, para_q, answer)
                new_items.append({"text": new_chatml})
                existing_questions.add(para_q)

    # If still not enough, create question variations with product context
    if len(new_items) < needed and product in PRODUCT_CONTEXT:
        contexts = PRODUCT_CONTEXT[product]

        question_templates = [
            "{}とは何ですか？",
            "{}の機能について教えてください。",
            "{}の使い方を説明してください。",
            "{}のメリットは何ですか？",
            "{}はどのような場面で使用しますか？",
            "{}の設定方法を教えてください。",
            "{}のトラブルシューティング方法は？",
            "{}と他の製品との違いは何ですか？",
        ]

        for ctx in contexts:
            for template in question_templates:
                if len(new_items) >= needed:
                    break
                q = template.format(ctx)
                if q not in existing_questions:
                    # Find a relevant answer from existing data
                    best_answer = None
                    best_score = 0
                    for item in existing_qa:
                        _, _, ans = extract_qa_from_chatml(item.get("text", ""))
                        # Score based on context word presence
                        score = sum(1 for c in contexts if c.lower() in ans.lower())
                        if score > best_score:
                            best_score = score
                            best_answer = ans

                    if best_answer:
                        product_name = product.replace("_v2", "").replace("_", " ").upper()
                        system = f"あなたは{product_name}製品の専門家アシスタントです。正確で詳細な技術情報を提供してください。"
                        new_chatml = format_chatml(system, q, best_answer)
                        new_items.append({"text": new_chatml})
                        existing_questions.add(q)

    return new_items


def main():
    print("[START] Paraphrase Augmentation")
    print("=" * 60)

    # Create output directory
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    stats = {}
    total_original = 0
    total_augmented = 0

    # Process each product
    for product_dir in V5_AUGMENTED_DIR.iterdir():
        if not product_dir.is_dir():
            continue

        product = product_dir.name
        train_file = product_dir / "train.json"

        if not train_file.exists():
            continue

        with open(train_file, "r", encoding="utf-8") as f:
            existing_data = json.load(f)

        original_count = len(existing_data)
        total_original += original_count

        # Determine target
        target = PRODUCTS_NEED_MORE.get(product, original_count)

        # Generate synthetic data
        synthetic_data = generate_synthetic_qa(product, existing_data, target)

        # Combine
        augmented_data = existing_data + synthetic_data

        # Save
        out_dir = OUTPUT_DIR / product
        out_dir.mkdir(parents=True, exist_ok=True)

        with open(out_dir / "train.json", "w", encoding="utf-8") as f:
            json.dump(augmented_data, f, ensure_ascii=False, indent=2)

        added = len(synthetic_data)
        total_augmented += len(augmented_data)

        if added > 0:
            print(f"  [DONE] {product}: {original_count} -> {len(augmented_data)} (+{added})")

        stats[product] = {
            "original": original_count,
            "augmented": len(augmented_data),
            "added": added,
        }

    # Save report
    report = {
        "summary": {
            "total_original": total_original,
            "total_augmented": total_augmented,
            "total_added": total_augmented - total_original,
        },
        "products": stats,
    }

    with open(OUTPUT_DIR / "paraphrase_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    print("\n" + "=" * 60)
    print("[REPORT] Paraphrase Augmentation Summary")
    print("=" * 60)
    print(f"Total Original: {total_original}")
    print(f"Total Augmented: {total_augmented}")
    print(f"Total Added: {total_augmented - total_original}")
    print(f"\nOutput: {OUTPUT_DIR}")
    print("[DONE] Paraphrase augmentation complete!")


if __name__ == "__main__":
    main()
