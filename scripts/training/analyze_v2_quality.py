#!/usr/bin/env python3
"""v2 데이터셋 품질 분석"""
import os
import sys
import io
import json
import re
from collections import Counter
from pathlib import Path

# Windows stdout encoding fix
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

def extract_qa_from_chatml(text):
    q_match = re.search(r'<\|im_start\|>user\n(.+?)<\|im_end\|>', text, re.DOTALL)
    a_match = re.search(r'<\|im_start\|>assistant\n(.+?)<\|im_end\|>', text, re.DOTALL)
    question = q_match.group(1).strip() if q_match else ""
    answer = a_match.group(1).strip() if a_match else ""
    return question, answer

def analyze(path):
    print(f"\n{'='*60}")
    print(f"Analyzing: {path}")
    print(f"{'='*60}")

    with open(path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    total = len(data)
    print(f"Total samples: {total:,}")

    # 분석
    seen_questions = {}
    seen_answers = {}
    placeholder_answers = []
    answer_lengths = []
    product_mentions = Counter()

    placeholder_patterns = [
        r'^.+はOpenFrameシステムの(concept|api|command|config|error|procedure|term)です。$',
        r'^.+はOpenFrameシステムの.+です。$',
        r'^Unknown$',
    ]
    placeholder_regex = [re.compile(p) for p in placeholder_patterns]

    for i, item in enumerate(data):
        text = item.get("text", "")
        q, a = extract_qa_from_chatml(text)

        if not q or not a:
            continue

        # 중복
        if q in seen_questions:
            pass
        seen_questions[q] = i

        if a in seen_answers:
            pass
        seen_answers[a] = i

        # 플레이스홀더
        is_placeholder = False
        for regex in placeholder_regex:
            if regex.match(a.strip()):
                is_placeholder = True
                placeholder_answers.append((i, q[:50], a))
                break

        answer_lengths.append(len(a))

        # 제품
        product_match = re.search(r'\*\*製品/Product\*\*:\s*(\S+)', a)
        if product_match:
            product_mentions[product_match.group(1)] += 1

    # 결과 출력
    q_dup = total - len(seen_questions)
    a_dup = total - len(seen_answers)

    print(f"\n--- Duplication Analysis ---")
    print(f"Unique questions: {len(seen_questions):,}")
    print(f"Duplicate questions: {q_dup:,} ({q_dup/total*100:.2f}%)")
    print(f"Unique answers: {len(seen_answers):,}")
    print(f"Duplicate answers: {a_dup:,} ({a_dup/total*100:.2f}%)")

    print(f"\n--- Quality Issues ---")
    print(f"Placeholder answers: {len(placeholder_answers):,} ({len(placeholder_answers)/total*100:.2f}%)")

    if placeholder_answers:
        print(f"\n  Sample placeholder answers:")
        for i, q, a in placeholder_answers[:3]:
            print(f"    [{i}] Q: {q}... → A: {a[:60]}...")

    print(f"\n--- Answer Length Distribution ---")
    if answer_lengths:
        avg_len = sum(answer_lengths) / len(answer_lengths)
        sorted_lens = sorted(answer_lengths)
        print(f"Average: {avg_len:.1f} chars")
        print(f"Min: {min(answer_lengths)}")
        print(f"Max: {max(answer_lengths)}")
        print(f"Median: {sorted_lens[len(sorted_lens)//2]}")

        short = sum(1 for l in answer_lengths if l < 50)
        medium = sum(1 for l in answer_lengths if 50 <= l < 200)
        long_ans = sum(1 for l in answer_lengths if l >= 200)
        print(f"Short (<50): {short:,} ({short/total*100:.2f}%)")
        print(f"Medium (50-200): {medium:,} ({medium/total*100:.2f}%)")
        print(f"Long (>=200): {long_ans:,} ({long_ans/total*100:.2f}%)")

    print(f"\n--- Top 10 Products ---")
    for product, count in product_mentions.most_common(10):
        print(f"  {product}: {count:,} ({count/total*100:.2f}%)")

    return {
        "total": total,
        "unique_questions": len(seen_questions),
        "duplicate_questions": q_dup,
        "unique_answers": len(seen_answers),
        "duplicate_answers": a_dup,
        "placeholder_answers": len(placeholder_answers),
        "avg_answer_length": avg_len if answer_lengths else 0,
        "products": dict(product_mentions.most_common(10))
    }

def main():
    base = Path(__file__).parent.parent.parent / "uploads" / "summaries"

    # v2 train.json 분석
    v2_train = base / "v2" / "train.json"
    if v2_train.exists():
        v2_result = analyze(str(v2_train))

    # 기존 train.json과 비교
    v1_train = base / "train.json"
    if v1_train.exists():
        v1_result = analyze(str(v1_train))

    # 비교 출력
    if v2_train.exists() and v1_train.exists():
        print(f"\n{'='*60}")
        print("COMPARISON: v1 vs v2")
        print(f"{'='*60}")
        print(f"{'Metric':<25} {'v1 (Old)':<20} {'v2 (New)':<20} {'Change':<15}")
        print("-" * 80)
        print(f"{'Total samples':<25} {v1_result['total']:,} {' '*10} {v2_result['total']:,} {' '*10} {v2_result['total']-v1_result['total']:+,}")
        print(f"{'Placeholder answers':<25} {v1_result['placeholder_answers']:,} ({v1_result['placeholder_answers']/v1_result['total']*100:.1f}%) {' '*2} {v2_result['placeholder_answers']:,} ({v2_result['placeholder_answers']/v2_result['total']*100:.1f}%)")
        print(f"{'Duplicate answers':<25} {v1_result['duplicate_answers']:,} ({v1_result['duplicate_answers']/v1_result['total']*100:.1f}%) {' '*2} {v2_result['duplicate_answers']:,} ({v2_result['duplicate_answers']/v2_result['total']*100:.1f}%)")
        print(f"{'Avg answer length':<25} {v1_result['avg_answer_length']:.1f} chars {' '*7} {v2_result['avg_answer_length']:.1f} chars")
        print("=" * 80)

if __name__ == "__main__":
    main()
